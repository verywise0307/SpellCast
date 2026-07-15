# SpellCast

SpellCast는 웹캠 손동작을 마법 입력으로 사용하는 Unreal Engine 5 PvP 게임이다.

## 폴더 역할

```text
SpellCast/
├─ matchmaking_server/  중앙 방 코드 매칭 서버
├─ client_bridge/       각 플레이어 PC의 로컬 연결 서버
├─ detect/              YOLO 손동작 인식기
├─ game/                Unreal 게임과 Listen Server
└─ server/              이전 명령 호환 및 모델 학습 파일
```

### matchmaking_server

- 인터넷 서버에서 한 번만 실행한다.
- 6자리 방 코드 생성, 참가, heartbeat, 방 종료만 처리한다.
- 카메라와 detector를 실행하지 않는다.
- HP, 마나, 피해를 판정하지 않는다.

### client_bridge

- 각 플레이어 PC에서 하나씩 실행한다.
- 주소는 `127.0.0.1:8000`만 사용한다.
- detector 실행 및 종료, 카메라 UI, 손동작 이벤트 전달을 담당한다.
- 카메라 이미지를 중앙 서버에 보내지 않는다.

### detect

- 같은 PC의 `client_bridge`에만 연결한다.
- 확정된 gesture를 `/cast`로 전송한다.
- UI용 JPEG 프레임을 `/camera/frame`으로 전송한다.

### game

- 방장은 `battlemap?listen`으로 Unreal Listen Server가 된다.
- Listen Server가 HP, 마나, 활성 슬롯, 피해, 승패를 최종 판정한다.
- 중앙 FastAPI 서버는 게임 판정을 하지 않는다.

## 1. 로컬 브리지 실행

각 플레이어 PC에서 실행한다.

```powershell
cd C:\Users\M\Desktop\SpellCast
python -m venv client_bridge\.venv
client_bridge\.venv\Scripts\python.exe -m pip install -r client_bridge\requirements.txt
client_bridge\.venv\Scripts\python.exe -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```

확인 주소:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/camera
```

Unreal Web Browser 위젯이 `/camera`를 열면 detector가 자동 실행된다. PIE가 끝나고 카메라 요청이 5초 동안 없으면 detector도 종료된다.

## 2. 중앙 매칭 서버 실행

개발 PC에서 시험할 때는 8100 포트를 사용한다.

```powershell
cd C:\Users\M\Desktop\SpellCast
python -m venv matchmaking_server\.venv
matchmaking_server\.venv\Scripts\python.exe -m pip install -r matchmaking_server\requirements.txt
matchmaking_server\.venv\Scripts\python.exe -m uvicorn matchmaking_server.main:app --host 0.0.0.0 --port 8100
```

확인 주소:

```text
http://127.0.0.1:8100/
http://127.0.0.1:8100/docs
```

## 3. detector 수동 실행

평소에는 로컬 브리지가 자동 실행한다. 디버그 창이 필요할 때만 수동 실행한다.

```powershell
detect\.venv\Scripts\python.exe detect\main.py --image-size 320 --show-window
```

## 주요 로컬 API

```text
POST /cast                 detector가 확정 손동작 전송
GET  /signal               Unreal이 최신 손동작 확인
GET  /camera               Unreal UI용 좌우 반전 영상 페이지
POST /camera/frame         detector가 JPEG 프레임 전송
POST /detector/start       detector 수동 시작
POST /detector/stop        detector 수동 종료
```

## 주요 매칭 API

```text
POST   /rooms                    방 생성
GET    /rooms/{code}             방 상태 확인
POST   /rooms/{code}/join        코드로 참가
POST   /rooms/{code}/heartbeat   방장 생존 알림
POST   /rooms/{code}/start       게임 시작 상태
POST   /rooms/{code}/close       방 종료
DELETE /rooms/{code}             방 종료
```

## 테스트

개발 의존성 설치 후 실행한다.

```powershell
matchmaking_server\.venv\Scripts\python.exe -m pip install -r matchmaking_server\requirements-dev.txt
matchmaking_server\.venv\Scripts\python.exe -m unittest discover -s matchmaking_server -p "test_*.py" -v
client_bridge\.venv\Scripts\python.exe -m pip install -r client_bridge\requirements-dev.txt
client_bridge\.venv\Scripts\python.exe -m unittest discover -s client_bridge -p "test_*.py" -v
```
