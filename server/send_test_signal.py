import argparse
import json
from urllib.request import Request, urlopen


GESTURES = [
    "fist",
    "palm",
    "peace",
    "rock",
    "like",
    "grip",
    "holy",
    "xsign",
    "hand_heart",
    "ok",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a confirmed test gesture.")
    parser.add_argument("gesture", choices=GESTURES)
    parser.add_argument("--player-id", default="player1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    payload = json.dumps(
        {
            "player_id": args.player_id,
            "gesture": args.gesture,
            "confidence": 1.0,
            "held_frames": 8,
        }
    ).encode("utf-8")
    request = Request(
        f"http://{args.host}:{args.port}/cast",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2.0) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
