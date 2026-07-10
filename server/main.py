from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class GestureSignal(BaseModel):
    gesture: str
    spell: str


app = FastAPI(title="SpellCast Signal Test")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_signal = GestureSignal(gesture="none", spell="none")
clients: set[WebSocket] = set()


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "SpellCast FastAPI signal server is running",
    }


@app.get("/signal")
def get_signal():
    return latest_signal


@app.post("/signal")
async def post_signal(signal: GestureSignal):
    global latest_signal
    latest_signal = signal

    disconnected: list[WebSocket] = []
    for client in clients:
        try:
            await client.send_json(signal.model_dump())
        except RuntimeError:
            disconnected.append(client)

    for client in disconnected:
        clients.discard(client)

    return {
        "received": True,
        "signal": latest_signal,
        "websocket_clients": len(clients),
    }


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
