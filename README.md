# SpellCast FastAPI to UE5 Signal Test

This first test checks whether Unreal Engine 5 can receive spell signals from a local FastAPI server.

## Run the Test Server

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open this URL to confirm the server is running:

```text
http://127.0.0.1:8000/
```

## Send a Test Signal

In another terminal:

```powershell
cd server
.\.venv\Scripts\Activate.ps1
python send_test_signal.py fist
```

Available gestures:

```text
fist, v, palm, thumb, index, both_hands
```

## UE5 HTTP Polling Test

The simplest UE5 test is polling this endpoint:

```text
GET http://127.0.0.1:8000/signal
```

Expected response:

```json
{
  "gesture": "fist",
  "spell": "fire_ball"
}
```

Recommended first Blueprint flow:

```text
Event BeginPlay
-> Set Timer by Event, 0.1 seconds looping
-> HTTP GET /signal
-> Parse JSON
-> If spell changed from previous spell
-> Print String or trigger placeholder spell effect
```

## UE5 WebSocket Test

For a more real-time version, connect UE5 to:

```text
ws://127.0.0.1:8000/ws
```

When `POST /signal` receives a new gesture, the server broadcasts the JSON payload to connected WebSocket clients.
