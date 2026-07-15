# Client Bridge

각 플레이어 PC에서 실행되는 로컬 서버다.

```text
Unreal ←→ client_bridge ←→ detector와 웹캠
```

- 반드시 `127.0.0.1:8000`으로만 실행한다.
- 카메라 이미지는 플레이어 PC 밖으로 보내지 않는다.
- `/camera`가 열리면 detector를 자동 실행한다.
- 카메라 요청이 5초간 없으면 자동 실행한 detector를 종료한다.
- 마나와 피해 같은 PvP 판정은 하지 않는다.

```powershell
client_bridge\.venv\Scripts\python.exe -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```
