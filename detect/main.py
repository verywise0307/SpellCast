import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cv2
from ultralytics import YOLO


GESTURE_LABELS = {
    "fist": "Fire Ball",
    "palm": "Wind Blast",
    "peace": "Ice Spear",
    "rock": "Lightning",
    "like": "Recovery",
    "grip": "Mana Drain",
    "holy": "Meteor",
    "xsign": "Arcane Barrier",
    "hand_heart": "Heart Sanctuary",
    "ok": "Mana Surge",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recognize HaGRID gestures and request SpellCast spells."
    )
    parser.add_argument(
        "--model",
        default=str(Path(__file__).with_name("hagrid-v2-yolov10n.pt")),
    )
    # detector는 중앙 매칭 서버가 아니라 같은 PC의 client_bridge로만 보낸다.
    parser.add_argument("--server", default="http://127.0.0.1:8000/cast")
    parser.add_argument("--player-id", default="player1")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--hold-seconds", type=float, default=0.8)
    parser.add_argument("--detect-fps", type=float, default=10.0)
    parser.add_argument(
        "--device",
        default="cpu",
        help="YOLO inference device. Use cpu to avoid competing with Unreal for the GPU.",
    )
    parser.add_argument("--image-size", type=int, default=300)
    # 카메라 원본도 인터넷으로 보내지 않고 localhost에만 보낸다.
    parser.add_argument("--preview-server", default="http://127.0.0.1:8000/camera/frame")
    parser.add_argument("--preview-fps", type=float, default=10.0)
    parser.add_argument("--preview-size", type=int, default=320)
    parser.add_argument("--status-server", default="http://127.0.0.1:8000/detection")
    parser.add_argument("--status-fps", type=float, default=10.0)
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Show the local OpenCV preview window for debugging.",
    )
    return parser.parse_args()


def best_mapped_detection(result, confidence: float):
    candidates = []
    if result.boxes is None:
        return None
    for index in range(len(result.boxes)):
        score = float(result.boxes.conf[index].item())
        class_id = int(result.boxes.cls[index].item())
        gesture = str(result.names[class_id])
        if score >= confidence and gesture in GESTURE_LABELS:
            box = tuple(map(int, result.boxes.xyxy[index].tolist()))
            candidates.append((score, gesture, box))
    if not candidates:
        return None
    score, gesture, box = max(candidates, key=lambda item: item[0])
    return gesture, score, box


def request_cast(
    server_url: str,
    player_id: str,
    gesture: str,
    confidence: float,
    held_frames: int,
    held_seconds: float,
) -> tuple[bool, str]:
    payload = json.dumps(
        {
            "player_id": player_id,
            "gesture": gesture,
            "confidence": confidence,
            "held_frames": held_frames,
            "held_seconds": held_seconds,
        }
    ).encode("utf-8")
    request = Request(
        server_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("accepted"):
            signal = data["signal"]
            return True, f"CAST {signal['spell']}"
        return False, f"REJECTED: {data.get('reason', 'unknown reason')}"
    except HTTPError as error:
        return False, f"SERVER ERROR: HTTP {error.code}"
    except (URLError, TimeoutError, json.JSONDecodeError):
        return False, "SERVER OFFLINE"


def send_preview_frame(server_url: str, frame) -> None:
    encoded, jpeg = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60]
    )
    if not encoded:
        return
    request = Request(
        server_url,
        data=jpeg.tobytes(),
        headers={"Content-Type": "image/jpeg"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=0.25):
            pass
    except (HTTPError, URLError, TimeoutError):
        pass


def make_square_preview(frame, size: int):
    """웹캠 중앙을 정사각형으로 잘라 작은 UI 전송용 프레임으로 만든다."""
    height, width = frame.shape[:2]
    edge = min(height, width)
    x = (width - edge) // 2
    y = (height - edge) // 2
    cropped = frame[y : y + edge, x : x + edge]
    return cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)


def send_detection_status(
    server_url: str,
    gesture: str | None,
    confidence: float,
    held_frames: int,
    required_frames: int,
    held_seconds: float,
    required_seconds: float,
) -> None:
    """현재 인식 상태를 같은 PC의 client_bridge에 전달한다."""
    payload = json.dumps(
        {
            "gesture": gesture or "none",
            "confidence": confidence if gesture else 0.0,
            "held_frames": held_frames if gesture else 0,
            "required_frames": required_frames,
            "held_seconds": held_seconds if gesture else 0.0,
            "required_seconds": required_seconds,
            "detected": gesture is not None,
        }
    ).encode("utf-8")
    request = Request(
        server_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=0.1):
            pass
    except (HTTPError, URLError, TimeoutError):
        pass


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if args.hold_seconds <= 0:
        raise ValueError("--hold-seconds must be greater than 0")
    if args.detect_fps <= 0:
        raise ValueError("--detect-fps must be greater than 0")
    if args.preview_size < 64:
        raise ValueError("--preview-size must be at least 64")

    model = YOLO(str(model_path))
    camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise RuntimeError(f"Could not open webcam index {args.camera}")
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    candidate = None
    candidate_started_at = None
    consecutive_frames = 0
    confirmed_while_held = None
    server_message = "Waiting for gesture"
    server_message_until = 0.0
    previous_time = time.perf_counter()
    next_preview_at = 0.0
    next_status_at = 0.0
    next_detection_at = time.perf_counter()
    required_frames = max(1, round(args.hold_seconds * args.detect_fps))
    fps = 0.0

    if args.show_window:
        print("Press Q or Esc to quit.")
    else:
        print("Detector running without a local preview window.")
    try:
        while True:
            now = time.perf_counter()
            if now < next_detection_at:
                time.sleep(next_detection_at - now)
            next_detection_at = time.perf_counter() + 1.0 / args.detect_fps

            ok, frame = camera.read()
            if not ok:
                break

            result = model.predict(
                frame,
                imgsz=args.image_size,
                device=args.device,
                verbose=False,
            )[0]
            detection = best_mapped_detection(result, args.confidence)
            live_gesture = None
            live_confidence = 0.0
            held_seconds = 0.0
            if detection is None:
                candidate = None
                candidate_started_at = None
                consecutive_frames = 0
                confirmed_while_held = None
                status = "No mapped gesture"
            else:
                gesture, score, (x1, y1, x2, y2) = detection
                live_gesture = gesture
                live_confidence = score
                if gesture == candidate:
                    consecutive_frames += 1
                else:
                    candidate = gesture
                    candidate_started_at = time.perf_counter()
                    consecutive_frames = 1
                    confirmed_while_held = None
                held_seconds = max(
                    0.0, time.perf_counter() - (candidate_started_at or time.perf_counter())
                )

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
                cv2.putText(
                    frame,
                    f"{gesture}: {GESTURE_LABELS[gesture]} ({score:.2f})",
                    (x1, max(25, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 220, 0),
                    2,
                )
                status = f"Hold {gesture}: {held_seconds:.1f}/{args.hold_seconds:.1f}s"

                if (
                    held_seconds >= args.hold_seconds
                    and confirmed_while_held != gesture
                ):
                    confirmed_while_held = gesture
                    accepted, server_message = request_cast(
                        args.server,
                        args.player_id,
                        gesture,
                        score,
                        consecutive_frames,
                        held_seconds,
                    )
                    server_message_until = time.perf_counter() + 2.5
                    status = "CONFIRMED" if accepted else "GESTURE CONFIRMED"
                    print(server_message)

            now = time.perf_counter()
            elapsed = now - previous_time
            previous_time = now
            if elapsed > 0:
                instant_fps = 1.0 / elapsed
                fps = instant_fps if fps == 0 else fps * 0.9 + instant_fps * 0.1

            cv2.putText(
                frame,
                status,
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
            )
            if now < server_message_until:
                cv2.putText(
                    frame,
                    server_message,
                    (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
            cv2.putText(
                frame,
                f"FPS {fps:.1f}",
                (20, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            if args.preview_fps > 0 and now >= next_preview_at:
                next_preview_at = now + 1.0 / args.preview_fps
                preview = make_square_preview(frame, args.preview_size)
                send_preview_frame(args.preview_server, preview)
            if args.status_fps > 0 and now >= next_status_at:
                next_status_at = now + 1.0 / args.status_fps
                send_detection_status(
                    args.status_server,
                    live_gesture,
                    live_confidence,
                    consecutive_frames,
                    required_frames,
                    held_seconds,
                    args.hold_seconds,
                )
            if args.show_window:
                cv2.imshow("SpellCast Detector", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
    finally:
        camera.release()
        if args.show_window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
