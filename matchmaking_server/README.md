# Matchmaking Server

인터넷에 배포하는 중앙 매칭 서버다.

```text
방장 Unreal → 6자리 코드 생성
참가자 Unreal → 코드 입력 → 방장 접속 주소 받기
```

- DB 없이 방을 메모리에 저장한다.
- 방장은 10초마다 heartbeat를 보낸다.
- 30초 동안 heartbeat가 없으면 방이 만료된다.
- detector, 카메라, HP, 마나, 피해는 처리하지 않는다.

```powershell
matchmaking_server\.venv\Scripts\python.exe -m uvicorn matchmaking_server.main:app --host 0.0.0.0 --port 8100
```
