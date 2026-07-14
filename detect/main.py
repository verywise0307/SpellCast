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
    parser.add_argument("--server", default="http://127.0.0.1:8000/cast")
    parser.add_argument("--player-id", default="player1")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--hold-frames", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=800)
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
) -> tuple[bool, str]:
    payload = json.dumps(
        {
            "player_id": player_id,
            "gesture": gesture,
            "confidence": confidence,
            "held_frames": held_frames,
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
            return True, f"CAST {signal['spell']} | mana {signal['mana']}"
        return False, f"REJECTED: {data.get('reason', 'unknown reason')}"
    except HTTPError as error:
        return False, f"SERVER ERROR: HTTP {error.code}"
    except (URLError, TimeoutError, json.JSONDecodeError):
        return False, "SERVER OFFLINE"


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if args.hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")

    model = YOLO(str(model_path))
    camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise RuntimeError(f"Could not open webcam index {args.camera}")

    candidate = None
    consecutive_frames = 0
    confirmed_while_held = None
    server_message = "Waiting for gesture"
    server_message_until = 0.0
    previous_time = time.perf_counter()
    fps = 0.0

    print("Press Q or Esc to quit.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                break

            result = model.predict(frame, imgsz=args.image_size, verbose=False)[0]
            detection = best_mapped_detection(result, args.confidence)
            if detection is None:
                candidate = None
                consecutive_frames = 0
                confirmed_while_held = None
                status = "No mapped gesture"
            else:
                gesture, score, (x1, y1, x2, y2) = detection
                if gesture == candidate:
                    consecutive_frames += 1
                else:
                    candidate = gesture
                    consecutive_frames = 1
                    confirmed_while_held = None

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
                status = f"Hold {gesture}: {consecutive_frames}/{args.hold_frames}"

                if (
                    consecutive_frames >= args.hold_frames
                    and confirmed_while_held != gesture
                ):
                    confirmed_while_held = gesture
                    accepted, server_message = request_cast(
                        args.server,
                        args.player_id,
                        gesture,
                        score,
                        consecutive_frames,
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
            cv2.imshow("SpellCast Detector", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
