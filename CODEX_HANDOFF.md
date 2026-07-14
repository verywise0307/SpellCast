# SpellCast Codex 인수인계

이 문서는 다른 PC의 Codex가 현재 프로젝트 상황을 빠르게 파악하고 작업을 이어가기 위한 인수인계 문서다.

## 1. 프로젝트 개요

SpellCast는 웹캠 손동작 인식을 이용하는 고정 위치 1대1 마법사 PvP 게임이다.

- 게임 엔진: Unreal Engine 5
- AI 인식: HaGRIDv2 기반 YOLOv10n gesture detector
- detector: Python, Ultralytics, OpenCV
- 신호 및 게임 상태 서버: FastAPI
- 플레이어 이동 없음
- 공격은 상대를 자동 지정
- 전투의 핵심은 코스트, 활성 마법 3개, 덱 순환, 공격과 방어 타이밍이다.

상세 기획은 루트의 `GAME_MECHANICS.txt`를 반드시 함께 읽는다.

## 2. 디렉터리 역할

```text
SpellCast/
├─ detect/                 # 플레이어 PC에서 실행되는 웹캠 AI
│  ├─ main.py
│  ├─ hagrid-v2-yolov10n.pt
│  ├─ requirements.txt
│  └─ README.txt
├─ server/                 # FastAPI 신호 및 게임 상태 서버
│  ├─ main.py
│  ├─ send_test_signal.py
│  └─ requirements.txt
├─ game/SpellCast/         # Unreal 프로젝트
├─ GAME_MECHANICS.txt      # 게임 기획 원본
└─ CODEX_HANDOFF.md        # 이 문서
```

AI 코드는 `server`가 아니라 `detect`에 둔다. detector는 플레이어 클라이언트와 함께 실행되는 companion process다. 카메라 영상은 서버에 전송하지 않는다.

## 3. 확정된 게임 규칙

- 전체 마법은 10개다.
- 경기 시작 전에 10개 중 6개를 덱으로 선택한다.
- 6개 중 앞의 3개만 현재 활성 상태다.
- 마법을 사용하면 덱 뒤로 이동하고 다음 마법이 활성화된다.
- 최대 코스트는 10이다.
- 시작 코스트 초안은 5다.
- 기본적으로 1.5초마다 코스트가 1 회복된다.
- 같은 손동작이 8프레임 연속 검출되어야 시전 요청을 보낸다.
- 손을 유지해도 한 번만 요청하며, 손을 풀거나 다른 동작으로 바뀌어야 다시 요청할 수 있다.
- 양손 마법은 한손 마법보다 비싸고 강력하다.
- 플레이어 이동과 수동 조준은 없다.

## 4. 마법 및 HaGRIDv2 매핑

| 번호 | HaGRIDv2 gesture | spell ID | 표시 이름 | 코스트 | 구분 |
|---:|---|---|---|---:|---|
| 1 | `fist` | `fire_ball` | 파이어볼 | 2 | 한손 |
| 2 | `palm` | `wind_blast` | 윈드 블라스트 | 2 | 한손 |
| 3 | `peace` | `ice_spear` | 아이스 스피어 | 3 | 한손 |
| 4 | `rock` | `lightning` | 라이트닝 | 4 | 한손 |
| 5 | `like` | `recovery` | 리커버리 | 4 | 한손 |
| 6 | `grip` | `mana_drain` | 마나 드레인 | 4 | 한손 |
| 7 | `holy` | `meteor` | 메테오 | 7 | 양손 |
| 8 | `xsign` | `arcane_barrier` | 아케인 배리어 | 6 | 양손 |
| 9 | `hand_heart` | `heart_sanctuary` | 하트 생추어리 | 7 | 양손 |
| 10 | `ok` | `mana_surge` | 마나 가속 | 3 | 한손 |

마법이 간섭하는 범위는 다음으로 제한한다.

- 투사체
- 방어막
- 상대 HP
- 내 HP
- 양쪽 코스트

이동 방해, 행동 불능, 활성 슬롯 봉인처럼 별도 복잡한 상태 시스템이 필요한 효과는 사용하지 않는다.

## 5. detector 구현

파일: `detect/main.py`

동작:

1. `detect/hagrid-v2-yolov10n.pt`를 로드한다.
2. 웹캠 프레임에서 매핑된 10개 gesture 중 신뢰도가 가장 높은 결과를 선택한다.
3. 동일 gesture가 기본 8프레임 연속 검출되면 서버의 `POST /cast`로 요청한다.
4. 같은 손을 계속 유지하는 동안 중복 요청하지 않는다.
5. 서버 승인 또는 거부 이유를 웹캠 화면과 터미널에 표시한다.

기본 실행:

```powershell
server\.venv\Scripts\python.exe detect\main.py
```

저사양 PC 실행 권장:

```powershell
server\.venv\Scripts\python.exe detect\main.py --image-size 416
```

종료 키는 `Q` 또는 `Esc`다.

detector가 전송하는 JSON:

```json
{
  "player_id": "player1",
  "gesture": "fist",
  "confidence": 0.91,
  "held_frames": 8
}
```

detector는 spell 이름이나 코스트를 결정하지 않는다. 서버가 gesture를 spell로 매핑한다.

## 6. FastAPI 서버 구현

파일: `server/main.py`

서버의 책임:

- gesture와 spell 매핑
- 최소 신뢰도 0.55 검증
- 8프레임 이상 검증
- 현재 활성 3슬롯 검증
- 코스트 회복 및 차감
- 6개 덱 순환
- 승인된 마법에 증가하는 `event_id` 부여
- Unreal이 조회하는 최신 `/signal` 갱신
- WebSocket 클라이언트 방송

서버 실행:

```powershell
server\.venv\Scripts\python.exe -m uvicorn main:app `
  --app-dir server `
  --host 127.0.0.1 `
  --port 8000
```

주요 API:

```text
GET  /                         서버 상태
POST /cast                     detector의 시전 요청
GET  /signal                   Unreal이 최신 승인 이벤트 조회
GET  /player/{player_id}       현재 코스트, 활성 마법, 덱 순서 조회
PUT  /player/{player_id}/loadout  6개 덱 설정
POST /reset                    전체 테스트 상태 초기화
WS   /ws                       승인 이벤트 실시간 방송
```

Unreal이 받는 `/signal` 예시:

```json
{
  "event_id": 1,
  "player_id": "player1",
  "gesture": "fist",
  "spell": "fire_ball",
  "cost": 2,
  "mana": 3,
  "active_spells": [
    "wind_blast",
    "ice_spear",
    "lightning"
  ]
}
```

기본 덱:

```text
fire_ball, wind_blast, ice_spear, lightning, recovery, meteor
```

기본 활성 3슬롯:

```text
fire_ball, wind_blast, ice_spear
```

따라서 처음에 `rock`, `holy`, `ok` 등을 인식하면 `spell is not in the active 3 slots`로 거부되는 것이 정상이다.

상태 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/player/player1
```

초기화:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/reset
```

웹캠 없이 fist 테스트:

```powershell
server\.venv\Scripts\python.exe server\send_test_signal.py fist
```

## 7. Unreal Blueprint 구조

현재 생성된 주요 Blueprint asset:

```text
/Game/blueprints/BP_gamemode
/Game/blueprints/BP_playercontroller
/Game/blueprints/ESpellID
/Game/Characters/witch/BP_witch
```

`ESpellID` 항목:

```text
FireBall
WindBlast
IceSpear
Lightning
Recovery
ManaDrain
Meteor
ArcaneBarrier
HeartSanctuary
ManaSurge
```

### BP_gamemode 필수 설정

```text
Default Pawn Class      = BP_witch
Player Controller Class = BP_playercontroller
```

맵 `testmap`의 World Settings:

```text
GameMode Override = BP_gamemode
```

한 번 `BP_playercontroller`가 GameMode에 등록되지 않아 HTTP와 모든 이벤트가 실행되지 않는 문제가 있었다. 학원 PC에서 반드시 이 설정을 다시 확인한다.

### BP_playercontroller 책임

- BeginPlay에서 반복 타이머 시작
- 0.5초 간격으로 `GET http://127.0.0.1:8000/signal`
- HTTP 완료 이벤트에서 성공 여부 확인
- JSON의 `event_id`와 `spell` 추출
- 새 event_id일 때만 spell 문자열을 `ESpellID`로 변환
- Controlled Pawn인 `BP_witch`에 `ExecuteSpell(SpellID)` 전달

안전한 HTTP 흐름:

```text
PollSpellSignal
→ RequestInFlight == false
→ RequestInFlight = true
→ Http Request

On Request Complete
→ RequestInFlight = false
→ Branch(bSuccessful)
   ├─ True  → JSON 파싱
   └─ False → JSON을 파싱하지 않고 종료 또는 오류 출력
```

중요:

- `Http Request` 노드의 오른쪽 실행 핀은 응답 성공 핀이 아니다.
- Return Value에서 `Assign On Request Complete` 또는 `Bind Event to On Request Complete`를 사용한다.
- 실패 응답을 JSON으로 파싱하지 않는다.
- 요청 진행 중 다음 요청을 시작하지 않는다.
- 폴링 간격은 0.1초가 아니라 0.5초를 권장한다.

서버 문자열을 Enum으로 바꾸는 흐름:

```text
Switch on String
├─ fire_ball       → ReceiveSpell(FireBall)
├─ wind_blast      → ReceiveSpell(WindBlast)
├─ ice_spear       → ReceiveSpell(IceSpear)
├─ lightning       → ReceiveSpell(Lightning)
├─ recovery        → ReceiveSpell(Recovery)
├─ mana_drain      → ReceiveSpell(ManaDrain)
├─ meteor          → ReceiveSpell(Meteor)
├─ arcane_barrier  → ReceiveSpell(ArcaneBarrier)
├─ heart_sanctuary → ReceiveSpell(HeartSanctuary)
└─ mana_surge      → ReceiveSpell(ManaSurge)
```

`ReceiveSpell`은 PlayerController에 있고, 실제 마법 분기는 캐릭터에 둔다.

```text
BP_playercontroller.ReceiveSpell(ESpellID)
→ Get Controlled Pawn
→ Cast To BP_witch
→ BP_witch.ExecuteSpell(ESpellID)
```

### BP_witch 책임

```text
ExecuteSpell(SpellID)
→ Switch on ESpellID
   ├─ FireBall       → Spell_FireBall
   ├─ WindBlast      → Spell_WindBlast
   ├─ IceSpear       → Spell_IceSpear
   ├─ Lightning      → Spell_Lightning
   ├─ Recovery       → Spell_Recovery
   ├─ ManaDrain      → Spell_ManaDrain
   ├─ Meteor         → Spell_Meteor
   ├─ ArcaneBarrier  → Spell_ArcaneBarrier
   ├─ HeartSanctuary → Spell_HeartSanctuary
   └─ ManaSurge      → Spell_ManaSurge
```

현재 각 마법 이벤트에는 연결 확인용 `Print String`이 달려 있다. detector와 서버 연결은 확인됐으며 Unreal 이벤트 수신도 사용자가 연결됐다고 확인했다.

## 8. 확인된 동작

- 공식 HaGRIDv2 YOLOv10n 모델에서 양손 동작 인식이 잘 된다.
- detector의 8프레임 확인이 동작한다.
- detector에서 `/cast`로 요청이 전달된다.
- 서버의 활성 3슬롯 검증이 동작한다.
- 승인된 마법은 `event_id`와 함께 `/signal`에 반영된다.
- 서버 상태 조회 결과 덱 순환이 정상 동작했다.
- Unreal PlayerController와 캐릭터 이벤트 연결이 완료됐다.

실제 확인했던 순환 예:

```text
초기:
fire_ball, wind_blast, ice_spear, lightning, recovery, meteor

fire_ball과 ice_spear 사용 후:
wind_blast, lightning, recovery, meteor, fire_ball, ice_spear
```

## 9. 저사양 학원 PC 대응

학원 PC에서 Unreal PIE와 YOLO를 동시에 실행하면 GPU 또는 VRAM 부족 가능성이 있다.

권장 순서:

1. FastAPI 서버 실행
2. `http://127.0.0.1:8000` 응답 확인
3. Unreal Editor 및 PIE 실행
4. detector를 낮은 이미지 크기로 실행

```powershell
server\.venv\Scripts\python.exe detect\main.py --image-size 416
```

필요하면 `--image-size 320`까지 낮춘다.

Unreal 설정:

```text
Engine Scalability Settings = Low 또는 Medium
Shadows, Global Illumination, Reflections, Effects 낮추기
```

D3D12 문제가 있으면 DX11 실행을 시험한다.

```powershell
UnrealEditor.exe D:\SpellCast\game\SpellCast\SpellCast.uproject -d3d11
```

크래시 또는 종료 분석 로그:

```text
game/SpellCast/Saved/Logs/SpellCast.log
```

판별 기준:

- `Out of video memory`, `D3D device lost`: GPU/VRAM 문제
- `Blueprint Runtime Error`: Blueprint 실행 문제
- `HttpBlueprint`: 요청 중첩 또는 HTTP 처리 문제
- 오류 없이 `BeginTearingDown`: 크래시가 아니라 정상 PIE 종료

## 10. 모델 관련 기록

처음에 잘못 받은 제3자 12클래스 모델은 양손 클래스를 지원하지 않았다. 사용하면 안 된다.

현재 사용해야 하는 모델:

```text
detect/hagrid-v2-yolov10n.pt
```

공식 출처:

```text
https://github.com/hukenovs/hagrid
```

공식 모델 다운로드 URL:

```text
https://rndml-team-cv.obs.ru-moscow-1.hc.sbercloud.ru/datasets/hagrid_v2/models/YOLOv10n_gestures.pt
```

## 11. 아직 구현하지 않은 것

- 실제 마법 Actor와 VFX
- 투사체 충돌 및 피해 판정
- HP UI와 코스트 UI
- 활성 3슬롯 UI와 덱 순환 애니메이션
- 서버의 HP, 방어막, 투사체 적중 결과 판정
- 멀티플레이 플레이어 인증 및 각 player_id 연결
- 실제 1대1 상대 연결
- 마법별 피해량, 회복량, 지속시간 최종 밸런스
- detector를 게임과 함께 자동 실행하는 런처 또는 패키징
- 학원 PC에서의 실제 성능 및 크래시 검증

현재 서버는 코스트와 덱 순환을 판정하고 승인된 spell 이벤트를 Unreal에 보낸다. HP와 투사체 판정은 아직 Unreal의 마법 Blueprint와 함께 구현해야 한다.

## 12. 다른 Codex에게 줄 시작 프롬프트

학원 PC에서 저장소를 pull한 후 다음과 같이 요청한다.

```text
CODEX_HANDOFF.md와 GAME_MECHANICS.txt를 처음부터 끝까지 읽어.
현재 SpellCast 구현과 확정된 설계를 파악한 뒤 이어서 작업해줘.
detect, server, game의 역할 분리를 유지하고 기존 사용자 Blueprint 및 에셋 변경을 보존해.
작업 전에 git status와 최신 파일을 확인하고, 인수인계 문서와 실제 코드가 다르면 실제 코드를 우선하되 차이를 보고해.
```

## 13. Git 주의사항

- 작업 트리에 Unreal 에셋 변경과 World Partition External Actor 삭제가 존재할 수 있다.
- 이 변경들은 사용자가 Unreal Editor에서 작업한 내용이므로 임의 복구하거나 삭제하지 않는다.
- `git reset --hard`, `git checkout --`, 무단 파일 삭제를 사용하지 않는다.
- `.venv`는 Git에 올리지 않는다.
- `.pt` 모델은 크기가 크므로 Git LFS 또는 다운로드 안내 방식 사용을 검토한다.
- 다른 PC로 이동하기 전 필요한 코드와 Blueprint를 반드시 커밋하고 push한다.
