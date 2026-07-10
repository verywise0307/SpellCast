import argparse
import json
import urllib.request


SPELL_BY_GESTURE = {
    "fist": "fire_ball",
    "v": "ice_spear",
    "palm": "wind_blast",
    "thumb": "heal",
    "index": "lightning",
    "both_hands": "ultimate",
}


def main():
    parser = argparse.ArgumentParser(description="Send a test gesture signal.")
    parser.add_argument("gesture", choices=sorted(SPELL_BY_GESTURE))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8000")
    args = parser.parse_args()

    payload = {
        "gesture": args.gesture,
        "spell": SPELL_BY_GESTURE[args.gesture],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://{args.host}:{args.port}/signal",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
