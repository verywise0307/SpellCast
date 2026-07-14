SpellCast detector
==================

역할
----
- 웹캠에서 HaGRIDv2 손동작을 인식한다.
- 동일 동작이 8프레임 연속 검출되면 FastAPI의 POST /cast로 전송한다.
- 마법 이름과 코스트는 detector가 결정하지 않고 서버가 검증한다.

실행
----
1) 서버 가상환경 준비 및 서버 실행
   python -m venv server\.venv
   server\.venv\Scripts\pip.exe install -r server\requirements.txt
   server\.venv\Scripts\python.exe -m uvicorn main:app --app-dir server --host 127.0.0.1 --port 8000

2) detector 가상환경 준비 및 detector 실행
   python -m venv detect\.venv
   detect\.venv\Scripts\pip.exe install -r detect\requirements.txt
   detect\.venv\Scripts\python.exe detect\main.py

종료: Q 또는 Esc

기본 모델
---------
detect\hagrid-v2-yolov10n.pt

Unreal 연동
-----------
- Unreal PlayerController는 GET http://127.0.0.1:8000/signal 을 반복 조회한다.
- event_id가 LastEventID와 다를 때만 spell 문자열을 ESpellID로 변환해 실행한다.
- 서버가 꺼져 있거나 bSuccessful이 false이면 JSON을 파싱하지 않는다.
