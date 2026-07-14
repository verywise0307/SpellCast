import argparse
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import cv2
from ultralytics import YOLO


SPELL_BY_GESTURE = {
    "fist": "fire_ball",
    "peace": "ice_spear",
    "palm": "wind_blast",
    "like": "heal",
    "point": "lightning",
    "grip": "ultimate",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test a HaGRID YOLO model with a webcam."
    )
    parser.add_argument(
        "--model",
        default=str(
            Path(__file__).resolve().parent.parent
            / "detect"
            / "hagrid-v2-yolov10n.pt"
        ),
        help="Path to the Ultralytics .pt model",
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument(
        "--hold-frames",
        type=int,
        default=8,
        help="Consecutive frames required to confirm a gesture",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="Optional FastAPI endpoint, e.g. http://127.0.0.1:8000/signal",
    )
    return parser.parse_args()


def post_signal(server_url: str, gesture: str) -> None:
    spell = SPELL_BY_GESTURE.get(gesture)
    if spell is None:
        print(f"[CONFIRMED] {gesture} (no spell mapping; not sent)")
        return

    body = json.dumps({"gesture": gesture, "spell": spell}).encode("utf-8")
    request = Request(
        server_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=1.0) as response:
            response.read()
        print(f"[SENT] {gesture} -> {spell}")
    except (URLError, TimeoutError) as error:
        print(f"[SEND FAILED] {error}")


def best_detection(result, confidence: float):
    if result.boxes is None or len(result.boxes) == 0:
        return None

    best_index = int(result.boxes.conf.argmax().item())
    score = float(result.boxes.conf[best_index].item())
    if score < confidence:
        return None

    class_id = int(result.boxes.cls[best_index].item())
    gesture = str(result.names[class_id])
    x1, y1, x2, y2 = map(int, result.boxes.xyxy[best_index].tolist())
    return gesture, score, (x1, y1, x2, y2)


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
    fps = 0.0
    previous_time = time.perf_counter()

    print("Press Q or Esc to quit.")
    print(f"Classes: {model.names}")

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Failed to read a webcam frame.")
                break

            result = model.predict(frame, imgsz=800, verbose=False)[0]
            detection = best_detection(result, args.confidence)

            if detection is None:
                candidate = None
                consecutive_frames = 0
                confirmed_while_held = None
                status = "No gesture"
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
                    f"{gesture} {score:.2f}",
                    (x1, max(25, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 220, 0),
                    2,
                )

                confirmed = consecutive_frames >= args.hold_frames
                status = (
                    f"CONFIRMED: {gesture}"
                    if confirmed
                    else f"Hold {gesture}: {consecutive_frames}/{args.hold_frames}"
                )

                if confirmed and confirmed_while_held != gesture:
                    confirmed_while_held = gesture
                    if args.server_url:
                        post_signal(args.server_url, gesture)
                    else:
                        print(f"[CONFIRMED] {gesture}")

            now = time.perf_counter()
            elapsed = now - previous_time
            previous_time = now
            if elapsed > 0:
                instant_fps = 1.0 / elapsed
                fps = instant_fps if fps == 0 else fps * 0.9 + instant_fps * 0.1

            color = (0, 255, 255) if "CONFIRMED" in status else (255, 255, 255)
            cv2.putText(
                frame,
                status,
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )
            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )
            cv2.imshow("SpellCast HaGRID Test", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
