# Client Bridge

각 플레이어 PC에서 실행되는 로컬 서버다.

```text
Unreal ←→ client_bridge ←→ detector와 웹캠
```

- 반드시 `127.0.0.1:8000`으로만 실행한다.
- 카메라 이미지는 플레이어 PC 밖으로 보내지 않는다.
- `/camera`가 열리면 detector를 자동 실행한다.
- 카메라 요청이 5초간 없으면 자동 실행한 detector를 종료한다.
- 카메라 UI는 320×320 JPEG를 최대 10FPS로 갱신한다.
- 마나와 피해 같은 PvP 판정은 하지 않는다.

## 실시간 손동작 UI API

detector는 현재 손동작과 누적 프레임을 `POST /detection`으로 보낸다.
Unreal UI는 `GET /detection`을 0.05~0.1초 간격으로 읽는다.

```json
{
  "gesture": "fist",
  "spell": "FireBall",
  "confidence": 0.87,
  "held_frames": 5,
  "required_frames": 8,
  "held_seconds": 0.5,
  "required_seconds": 0.8,
  "detected": true,
  "progress": 0.625,
  "confirmed": false
}
```

탐지는 0.1초 간격(10FPS)으로 실행되고 동일 손동작을 0.8초 유지하면 확정된다.
0.5초 동안 detector 갱신이 없으면 미탐지 상태가 반환된다. UMG 진행률에는
시간 기준으로 계산된 `progress`를 그대로 사용하면 된다.

```powershell
client_bridge\.venv\Scripts\python.exe -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```
