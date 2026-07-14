# SpellCast

SpellCast는 웹캠으로 인식한 손동작을 Unreal Engine 5 안의 마법 입력으로 연결하는 실시간 PvP 액션 게임 프로젝트입니다.

현재 단계에서는 YOLO 모델을 붙이기 전에, 먼저 **FastAPI에서 보낸 신호를 UE5가 받을 수 있는지** 확인하는 테스트 서버를 구성합니다.

# 모델 출처

https://github.com/hukenovs/hagrid

## 현재 프로젝트 목표

```text
FastAPI
-> gesture / spell 신호 생성
-> UE5에서 HTTP 또는 WebSocket으로 수신
-> Print String 또는 임시 마법 발동
```

## 폴더 구조

```text
SpellCast/
├─ server/
│  ├─ main.py
│  ├─ requirements.txt
│  └─ send_test_signal.py
├─ .gitignore
└─ README.md
```

## FastAPI 서버 실행

처음 실행하는 경우:

```powershell
cd C:\Users\M\Desktop\SpellCast\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

이미 가상환경과 패키지 설치가 끝난 경우:

```powershell
cd C:\Users\M\Desktop\SpellCast\server
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000
```

서버가 정상 실행되면 아래 주소에서 상태를 확인할 수 있습니다.

```text
http://127.0.0.1:8000/
```

## 테스트 신호 보내기

서버를 켜둔 상태에서 새 터미널을 열고 실행합니다.

```powershell
cd C:\Users\M\Desktop\SpellCast\server
.\.venv\Scripts\Activate.ps1
python send_test_signal.py fist
```

사용 가능한 손동작 값:

```text
fist, v, palm, thumb, index, both_hands
```

각 손동작은 현재 아래 마법 신호로 변환됩니다.

```text
fist       -> fire_ball
v          -> ice_spear
palm       -> wind_blast
thumb      -> heal
index      -> lightning
both_hands -> ultimate
```

## UE5 HTTP 수신 테스트

가장 먼저 추천하는 방식은 UE5에서 아래 주소를 반복해서 읽는 것입니다.

```text
GET http://127.0.0.1:8000/signal
```

예상 응답:

```json
{
  "gesture": "fist",
  "spell": "fire_ball"
}
```

추천 Blueprint 흐름:

```text
Event BeginPlay
-> Set Timer by Event, 0.1초 반복
-> HTTP GET /signal
-> JSON 파싱
-> 이전 spell 값과 다르면
-> Print String 또는 임시 마법 발동
```

이 단계에서는 실제 마법 이펙트보다 `fire_ball`, `ice_spear` 같은 문자열이 UE5 화면에 찍히는지 확인하는 것이 중요합니다.

## UE5 WebSocket 수신 테스트

더 실시간에 가까운 방식이 필요하면 WebSocket을 사용할 수 있습니다.

```text
ws://127.0.0.1:8000/ws
```

`POST /signal`로 새 손동작 신호가 들어오면, 서버는 연결된 WebSocket 클라이언트에게 아래 형태의 JSON을 전송합니다.

```json
{
  "gesture": "fist",
  "spell": "fire_ball"
}
```

초기 테스트는 HTTP 방식으로 먼저 성공시킨 뒤, 반응 속도가 부족하다고 느껴질 때 WebSocket으로 넘어가는 것을 추천합니다.

## 다음 단계

1. UE5에서 `/signal` 값을 받아 `Print String`으로 출력
2. spell 값이 바뀔 때만 이벤트 발생
3. `fire_ball` 신호를 임시 투사체 발사로 연결
4. YOLO 손동작 인식 결과를 `POST /signal`로 연결
5. 쿨타임, 마나, 오발동 방지 로직 추가
