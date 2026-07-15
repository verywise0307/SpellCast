"""6자리 코드로 두 플레이어를 연결하는 중앙 매칭 서버.

이 서버는 카메라, 손동작, HP, 마나를 처리하지 않는다.
방을 만들고 참가자에게 방장 Unreal의 접속 주소만 알려준다.
"""

import asyncio
import secrets
import time
from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator


# 방장이 30초 동안 heartbeat를 보내지 않으면 방을 삭제한다.
ROOM_TTL_SECONDS = 30.0
MAX_PLAYERS = 2


class CreateRoomRequest(BaseModel):
    """방 만들기 버튼을 눌렀을 때 보내는 값."""

    host_name: str = Field(min_length=1, max_length=24)
    connection: str = Field(min_length=1, max_length=256)

    @field_validator("host_name", "connection")
    @classmethod
    def remove_outer_spaces(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("빈 문자열은 사용할 수 없습니다")
        return value


class JoinRoomRequest(BaseModel):
    """6자리 코드로 참가할 때 보내는 값."""

    player_name: str = Field(min_length=1, max_length=24)

    @field_validator("player_name")
    @classmethod
    def remove_outer_spaces(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("빈 이름은 사용할 수 없습니다")
        return value


class HostRequest(BaseModel):
    """방장만 할 수 있는 요청에 사용하는 비밀 토큰."""

    host_token: str = Field(min_length=1)


class HeartbeatRequest(HostRequest):
    # 방장의 접속 주소가 바뀌었을 때 함께 갱신할 수 있다.
    connection: str | None = Field(default=None, min_length=1, max_length=256)


@dataclass
class Room:
    """메모리에 잠깐 저장되는 방 한 개의 상태."""

    code: str
    host_name: str
    connection: str
    host_token: str
    last_heartbeat_at: float
    guest_name: str | None = None
    game_status: str = "waiting"

    @property
    def player_count(self) -> int:
        return 1 if self.guest_name is None else 2


app = FastAPI(title="SpellCast Matchmaking Server")

# DB 대신 메모리에만 방을 저장한다. 서버가 재시작되면 모두 사라진다.
rooms: dict[str, Room] = {}
rooms_lock = asyncio.Lock()


def normalize_code(code: str) -> str:
    """방 코드가 정확히 숫자 6자리인지 확인한다."""
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail="방 코드는 숫자 6자리여야 합니다")
    return code


def delete_expired_rooms(now: float | None = None) -> None:
    """heartbeat가 끊긴 오래된 방을 메모리에서 지운다."""
    now = time.monotonic() if now is None else now
    expired = [
        code
        for code, room in rooms.items()
        if now - room.last_heartbeat_at >= ROOM_TTL_SECONDS
    ]
    for code in expired:
        del rooms[code]


def find_room(code: str) -> Room:
    """방을 찾고, 없으면 Unreal이 처리하기 쉬운 404를 반환한다."""
    room = rooms.get(normalize_code(code))
    if room is None:
        raise HTTPException(status_code=404, detail="방이 없거나 만료되었습니다")
    return room


def check_host_token(room: Room, token: str) -> None:
    """방장 토큰이 맞는지 안전하게 비교한다."""
    if not secrets.compare_digest(room.host_token, token):
        raise HTTPException(status_code=403, detail="방장 토큰이 올바르지 않습니다")


def new_room_code() -> str:
    """현재 사용 중이지 않은 6자리 코드를 만든다."""
    for _ in range(100):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if code not in rooms:
            return code
    raise HTTPException(status_code=503, detail="방 코드를 만들 수 없습니다")


def room_payload(room: Room) -> dict:
    """host_token과 접속 주소를 제외한 공개 방 정보."""
    remaining = ROOM_TTL_SECONDS - (time.monotonic() - room.last_heartbeat_at)
    return {
        "code": room.code,
        "host_name": room.host_name,
        "guest_name": room.guest_name,
        "player_count": room.player_count,
        "max_players": MAX_PLAYERS,
        "status": room.game_status,
        "expires_in": max(0, int(remaining)),
    }


@app.get("/")
def root():
    return {"status": "ok", "role": "matchmaking_server"}


@app.post("/rooms", status_code=status.HTTP_201_CREATED)
async def create_room(request: CreateRoomRequest):
    """새 방을 만들고 6자리 코드와 방장 토큰을 반환한다."""
    async with rooms_lock:
        delete_expired_rooms()
        now = time.monotonic()
        room = Room(
            code=new_room_code(),
            host_name=request.host_name,
            connection=request.connection,
            host_token=secrets.token_urlsafe(32),
            last_heartbeat_at=now,
        )
        rooms[room.code] = room
        return {
            **room_payload(room),
            "host_token": room.host_token,
            "heartbeat_interval": 10,
        }


@app.get("/rooms/{code}")
async def get_room(code: str):
    """코드에 해당하는 방의 대기 상태를 확인한다."""
    async with rooms_lock:
        delete_expired_rooms()
        return room_payload(find_room(code))


@app.post("/rooms/{code}/join")
async def join_room(code: str, request: JoinRoomRequest):
    """두 번째 플레이어를 넣고 방장 Unreal 접속 주소를 알려준다."""
    async with rooms_lock:
        delete_expired_rooms()
        room = find_room(code)
        if room.game_status != "waiting":
            raise HTTPException(status_code=409, detail="이미 시작한 방입니다")
        if room.guest_name is not None:
            raise HTTPException(status_code=409, detail="방이 가득 찼습니다")
        if room.host_name == request.player_name:
            raise HTTPException(status_code=409, detail="이미 사용 중인 이름입니다")
        room.guest_name = request.player_name
        return {**room_payload(room), "connection": room.connection}


@app.post("/rooms/{code}/heartbeat")
async def heartbeat(code: str, request: HeartbeatRequest):
    """방장이 살아 있음을 알린다. 권장 호출 주기는 10초다."""
    async with rooms_lock:
        delete_expired_rooms()
        room = find_room(code)
        check_host_token(room, request.host_token)
        if request.connection:
            room.connection = request.connection.strip()
        room.last_heartbeat_at = time.monotonic()
        return {"alive": True, **room_payload(room)}


@app.post("/rooms/{code}/start")
async def start_room(code: str, request: HostRequest):
    """두 명이 모인 방을 playing 상태로 바꾼다."""
    async with rooms_lock:
        delete_expired_rooms()
        room = find_room(code)
        check_host_token(room, request.host_token)
        if room.guest_name is None:
            raise HTTPException(status_code=409, detail="두 번째 플레이어를 기다리는 중입니다")
        room.game_status = "playing"
        room.last_heartbeat_at = time.monotonic()
        return room_payload(room)


@app.post("/rooms/{code}/close")
async def close_room(code: str, request: HostRequest):
    """Blueprint에서 사용하기 쉬운 POST 방식의 방 종료 API."""
    async with rooms_lock:
        delete_expired_rooms()
        room = find_room(code)
        check_host_token(room, request.host_token)
        del rooms[room.code]
        return {"closed": True, "code": room.code}


@app.delete("/rooms/{code}")
async def delete_room(code: str, host_token: str = Header(alias="X-Host-Token")):
    """표준 HTTP DELETE 방식도 함께 지원한다."""
    async with rooms_lock:
        delete_expired_rooms()
        room = find_room(code)
        check_host_token(room, host_token)
        del rooms[room.code]
        return {"closed": True, "code": room.code}
