"""Unreal과 detector 사이를 연결하는 플레이어 PC 전용 서버.

이 서버는 반드시 각 플레이어 PC에서 실행한다.
외부 인터넷에 공개하지 않고 127.0.0.1로만 사용한다.
"""

import atexit
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


# detector와 서버가 모두 사용하는 손동작 → 마법 이름 표다.
# 실제 마나, 활성 슬롯, 피해 판정은 Unreal Listen Server가 담당해야 한다.
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

REQUIRED_HOLD_FRAMES = 8
MIN_CONFIDENCE = 0.55


class GestureRequest(BaseModel):
    """detector가 동작을 확정한 뒤 보내는 데이터."""

    player_id: str = "local_player"
    gesture: str
    confidence: float = Field(ge=0.0, le=1.0)
    held_frames: int = Field(ge=1)


class LocalSignal(BaseModel):
    """Unreal이 /signal에서 읽는 가장 최근 입력."""

    event_id: int = 0
    player_id: str = "none"
    gesture: str = "none"
    spell: str = "none"


app = FastAPI(title="SpellCast Client Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_signal = LocalSignal()
next_event_id = 1
last_signal_read_at = 0.0

# detector가 보내는 최신 JPEG 한 장을 메모리에 보관한다.
latest_camera_frame: bytes | None = None
latest_camera_frame_at = 0.0
last_camera_view_at = 0.0

# 브리지가 직접 실행한 detector 프로세스를 기억한다.
detector_process: subprocess.Popen | None = None
detector_lock = threading.Lock()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DETECTOR_SCRIPT = PROJECT_ROOT / "detect" / "main.py"
DETECTOR_PYTHON = PROJECT_ROOT / "detect" / ".venv" / "Scripts" / "python.exe"


def detector_is_running() -> bool:
    """브리지가 실행한 detector가 아직 살아 있는지 확인한다."""
    return detector_process is not None and detector_process.poll() is None


def start_detector() -> bool:
    """detector를 창 없이 한 번만 실행한다."""
    global detector_process

    # 이미 외부에서 detector가 프레임을 보내고 있으면 중복 실행하지 않는다.
    if time.monotonic() - latest_camera_frame_at < 2.0:
        return False

    with detector_lock:
        if detector_is_running():
            return False

        python = DETECTOR_PYTHON if DETECTOR_PYTHON.is_file() else Path(sys.executable)
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        detector_process = subprocess.Popen(
            [str(python), str(DETECTOR_SCRIPT), "--image-size", "320"],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return True


def stop_detector() -> bool:
    """브리지가 실행했던 detector를 안전하게 종료한다."""
    global detector_process
    with detector_lock:
        process = detector_process
        detector_process = None

    if process is None or process.poll() is not None:
        return False

    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
    return True


def detector_idle_watcher() -> None:
    """PIE가 끝나 카메라 요청이 끊기면 detector를 자동 종료한다."""
    while True:
        time.sleep(1.0)
        if last_camera_view_at and time.monotonic() - last_camera_view_at > 5.0:
            stop_detector()


threading.Thread(target=detector_idle_watcher, daemon=True).start()
atexit.register(stop_detector)


@app.get("/")
def root():
    return {
        "status": "ok",
        "role": "client_bridge",
        "detector_running": detector_is_running(),
    }


@app.post("/cast")
def receive_gesture(request: GestureRequest):
    """확정된 손동작을 Unreal이 읽을 수 있는 이벤트로 바꾼다."""
    global latest_signal, next_event_id

    gesture = request.gesture.strip().lower()
    spell = SPELL_BY_GESTURE.get(gesture)
    if spell is None:
        raise HTTPException(status_code=400, detail="등록되지 않은 손동작입니다")
    if request.confidence < MIN_CONFIDENCE:
        return {"accepted": False, "reason": "신뢰도가 너무 낮습니다"}
    if request.held_frames < REQUIRED_HOLD_FRAMES:
        return {"accepted": False, "reason": "손동작 유지 프레임이 부족합니다"}

    signal = LocalSignal(
        event_id=next_event_id,
        player_id=request.player_id,
        gesture=gesture,
        spell=spell,
    )
    next_event_id += 1
    latest_signal = signal
    return {"accepted": True, "signal": signal}


def clear_signal_state() -> None:
    """이전 PIE에서 남은 마지막 손동작을 지운다."""
    global latest_signal, next_event_id
    latest_signal = LocalSignal()
    next_event_id = 1


@app.get("/signal", response_model=LocalSignal)
def get_signal():
    """Unreal PlayerController가 반복 조회하는 로컬 입력 API."""
    global last_signal_read_at
    now = time.monotonic()

    # Unreal은 PIE 중 약 0.5초마다 이 API를 읽는다.
    # 2초 넘게 요청이 없다가 다시 들어오면 새 PIE가 시작된 것으로 본다.
    # 이때 이전 PIE의 마지막 마법을 먼저 지워 재시전을 막는다.
    if last_signal_read_at and now - last_signal_read_at > 2.0:
        clear_signal_state()
    last_signal_read_at = now
    return latest_signal


@app.post("/reset")
def reset_signal():
    """에디터 테스트를 다시 시작할 때 이벤트 번호를 초기화한다."""
    clear_signal_state()
    return {"reset": True}


@app.post("/camera/frame")
async def update_camera_frame(request: Request):
    """detector가 보낸 JPEG 프레임 한 장을 저장한다."""
    global latest_camera_frame, latest_camera_frame_at
    frame = await request.body()
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise HTTPException(status_code=400, detail="JPEG 이미지가 아닙니다")
    if len(frame) > 2_000_000:
        raise HTTPException(status_code=413, detail="카메라 이미지가 너무 큽니다")
    latest_camera_frame = frame
    latest_camera_frame_at = time.monotonic()
    return Response(status_code=204)


@app.get("/camera/latest.jpg")
def get_camera_frame():
    """Unreal Web Browser 위젯이 최신 카메라 이미지를 가져간다."""
    global last_camera_view_at
    last_camera_view_at = time.monotonic()
    # detector가 꺼졌다면 다음 이미지 요청에서 자동으로 다시 살린다.
    if time.monotonic() - latest_camera_frame_at >= 2.0:
        start_detector()
    if latest_camera_frame is None:
        return Response(status_code=404)
    return Response(
        content=latest_camera_frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/camera", response_class=HTMLResponse)
def camera_page():
    """300×300 UI에 넣을 좌우 반전 카메라 페이지."""
    global last_camera_view_at
    last_camera_view_at = time.monotonic()
    start_detector()
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}
img{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
</style>
</head>
<body>
<img id="camera" alt="SpellCast camera preview">
<script>
const image=document.getElementById('camera');
function refresh(){image.src='/camera/latest.jpg?t='+Date.now()}
image.onload=()=>setTimeout(refresh,20);
image.onerror=()=>setTimeout(refresh,100);
refresh();
</script>
</body>
</html>"""


@app.post("/detector/start")
def start_detector_api():
    """필요할 때 Unreal에서 detector를 명시적으로 시작할 수도 있다."""
    started = start_detector()
    return {"started": started, "running": detector_is_running()}


@app.post("/detector/stop")
def stop_detector_api():
    """필요할 때 Unreal에서 detector를 명시적으로 종료할 수도 있다."""
    stopped = stop_detector()
    return {"stopped": stopped, "running": detector_is_running()}
