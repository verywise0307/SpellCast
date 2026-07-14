import asyncio
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


MAX_MANA = 10
STARTING_MANA = 5
MANA_REGEN_INTERVAL_SECONDS = 1.5
MANA_SURGE_SECONDS = 6.0
REQUIRED_HOLD_FRAMES = 8
MIN_CONFIDENCE = 0.55

SPELL_BY_GESTURE = {
    "fist": "fire_ball",
    "palm": "wind_blast",
    "peace": "ice_spear",
    "rock": "lightning",
    "like": "recovery",
    "grip": "mana_drain",
    "holy": "meteor",
    "xsign": "arcane_barrier",
    "hand_heart": "heart_sanctuary",
    "ok": "mana_surge",
}

SPELL_COST = {
    "fire_ball": 2,
    "wind_blast": 2,
    "ice_spear": 3,
    "lightning": 4,
    "recovery": 4,
    "mana_drain": 4,
    "meteor": 7,
    "arcane_barrier": 6,
    "heart_sanctuary": 7,
    "mana_surge": 3,
}

DEFAULT_LOADOUT = [
    "fire_ball",
    "wind_blast",
    "ice_spear",
    "lightning",
    "recovery",
    "meteor",
]


class GestureCastRequest(BaseModel):
    player_id: str = "player1"
    gesture: str
    confidence: float = Field(ge=0.0, le=1.0)
    held_frames: int = Field(ge=1)


class LegacyGestureSignal(BaseModel):
    gesture: str
    spell: str


class LoadoutRequest(BaseModel):
    spells: list[str]


class UnrealSignal(BaseModel):
    event_id: int = 0
    player_id: str = "none"
    gesture: str = "none"
    spell: str = "none"
    cost: int = 0
    mana: int = STARTING_MANA
    active_spells: list[str] = Field(default_factory=list)


@dataclass
class PlayerState:
    mana: int = STARTING_MANA
    cycle: list[str] = field(default_factory=lambda: DEFAULT_LOADOUT.copy())
    last_regen_at: float = field(default_factory=time.monotonic)
    mana_surge_until: float = 0.0

    @property
    def active_spells(self) -> list[str]:
        return self.cycle[:3]

    def regenerate(self, now: float) -> None:
        while now - self.last_regen_at >= MANA_REGEN_INTERVAL_SECONDS:
            self.last_regen_at += MANA_REGEN_INTERVAL_SECONDS
            amount = 2 if self.last_regen_at <= self.mana_surge_until else 1
            self.mana = min(MAX_MANA, self.mana + amount)

    def rotate(self, spell: str) -> None:
        self.cycle.remove(spell)
        self.cycle.append(spell)


app = FastAPI(title="SpellCast Game Signal Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

players: dict[str, PlayerState] = {}
clients: set[WebSocket] = set()
latest_signal = UnrealSignal()
next_event_id = 1
state_lock = asyncio.Lock()


def get_player(player_id: str) -> PlayerState:
    if player_id not in players:
        players[player_id] = PlayerState()
    return players[player_id]


def player_payload(player_id: str, player: PlayerState) -> dict:
    now = time.monotonic()
    player.regenerate(now)
    return {
        "player_id": player_id,
        "mana": player.mana,
        "max_mana": MAX_MANA,
        "active_spells": player.active_spells,
        "loadout_cycle": player.cycle,
        "mana_surge_active": now < player.mana_surge_until,
    }


async def broadcast(signal: UnrealSignal) -> None:
    disconnected: list[WebSocket] = []
    for client in tuple(clients):
        try:
            await client.send_json(signal.model_dump())
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        clients.discard(client)


async def approve_cast(
    player_id: str, gesture: str, spell: str, held_frames: int
) -> tuple[UnrealSignal | None, str | None]:
    global latest_signal, next_event_id

    if held_frames < REQUIRED_HOLD_FRAMES:
        return None, f"gesture must be held for {REQUIRED_HOLD_FRAMES} frames"
    if SPELL_BY_GESTURE.get(gesture) != spell:
        return None, "gesture and spell do not match"

    async with state_lock:
        player = get_player(player_id)
        now = time.monotonic()
        player.regenerate(now)
        if spell not in player.active_spells:
            return None, "spell is not in the active 3 slots"

        cost = SPELL_COST[spell]
        if player.mana < cost:
            return None, "not enough mana"

        player.mana -= cost
        if spell == "mana_surge":
            player.mana_surge_until = now + MANA_SURGE_SECONDS
        player.rotate(spell)

        signal = UnrealSignal(
            event_id=next_event_id,
            player_id=player_id,
            gesture=gesture,
            spell=spell,
            cost=cost,
            mana=player.mana,
            active_spells=player.active_spells,
        )
        next_event_id += 1
        latest_signal = signal

    await broadcast(signal)
    return signal, None


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "SpellCast game signal server is running",
        "required_hold_frames": REQUIRED_HOLD_FRAMES,
    }


@app.get("/signal", response_model=UnrealSignal)
def get_signal():
    """Unreal polls this endpoint and compares event_id with LastEventID."""
    return latest_signal


@app.post("/cast")
async def cast_from_detector(request: GestureCastRequest):
    if request.confidence < MIN_CONFIDENCE:
        return {
            "accepted": False,
            "reason": f"confidence must be at least {MIN_CONFIDENCE}",
            "state": player_payload(request.player_id, get_player(request.player_id)),
        }
    gesture = request.gesture.strip().lower()
    spell = SPELL_BY_GESTURE.get(gesture)
    if spell is None:
        raise HTTPException(status_code=400, detail="gesture is not mapped to a spell")

    signal, reason = await approve_cast(
        request.player_id, gesture, spell, request.held_frames
    )
    player = get_player(request.player_id)
    if signal is None:
        return {
            "accepted": False,
            "reason": reason,
            "state": player_payload(request.player_id, player),
        }
    return {
        "accepted": True,
        "signal": signal,
        "state": player_payload(request.player_id, player),
    }


@app.post("/signal")
async def post_legacy_signal(signal: LegacyGestureSignal):
    """Compatibility endpoint for send_test_signal.py."""
    approved, reason = await approve_cast(
        "player1", signal.gesture.strip().lower(), signal.spell.strip().lower(), 8
    )
    if approved is None:
        return {"accepted": False, "reason": reason}
    return {"accepted": True, "signal": approved}


@app.get("/player/{player_id}")
async def get_player_state(player_id: str):
    async with state_lock:
        return player_payload(player_id, get_player(player_id))


@app.put("/player/{player_id}/loadout")
async def set_loadout(player_id: str, request: LoadoutRequest):
    spells = [spell.strip().lower() for spell in request.spells]
    if len(spells) != 6 or len(set(spells)) != 6:
        raise HTTPException(status_code=400, detail="loadout must contain 6 unique spells")
    unknown = [spell for spell in spells if spell not in SPELL_COST]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown spells: {unknown}")
    async with state_lock:
        player = get_player(player_id)
        player.cycle = spells
        return player_payload(player_id, player)


@app.post("/reset")
async def reset_game():
    global latest_signal, next_event_id
    async with state_lock:
        players.clear()
        latest_signal = UnrealSignal()
        next_event_id = 1
    await broadcast(latest_signal)
    return {"reset": True}


@app.websocket("/ws")
async def websocket_signal(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    await websocket.send_json(latest_signal.model_dump())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.discard(websocket)
    except Exception:
        clients.discard(websocket)
