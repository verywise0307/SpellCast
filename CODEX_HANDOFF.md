# SpellCast Codex 인수인계

최종 갱신: 2026-07-15

이 문서는 다른 PC에서 프로젝트를 이어서 작업하기 위한 최신 상태 기록이다. 실제 코드와 루트 `README.md`가 이 문서와 다르면 실제 코드를 우선한다.

## 프로젝트 개요

SpellCast는 손동작 인식을 사용하는 고정 위치 1대1 마법 PvP 게임이다.

- 게임: Unreal Engine 5 Listen Server
- 손동작 인식: HaGRIDv2 기반 YOLO detector
- 로컬 연결: 각 플레이어 PC의 FastAPI client bridge
- 중앙 서버: 6자리 코드 기반 matchmaking server
- 플레이어 이동과 별도 쿨다운 규칙은 없다.
- 6개 주문 중 앞의 3개만 활성 슬롯이며, 사용한 주문은 배열 맨 뒤로 이동한다.

## 현재 폴더 구조

```text
SpellCast/
├─ matchmaking_server/  # 중앙 FastAPI 매칭 서버
├─ client_bridge/       # 각 플레이어 PC의 로컬 FastAPI
├─ detect/              # YOLO 손동작 인식
├─ game/SpellCast/      # Unreal 게임과 Listen Server
└─ server/              # 이전 실행 방식 호환용
```

역할은 다음과 같다.

- `matchmaking_server`: 메모리에 6자리 방 코드를 만들고 참가, 하트비트, 시작, 닫기를 처리한다. 현재 DB는 사용하지 않는다.
- `client_bridge`: `127.0.0.1:8000`에서 해당 PC의 detector와 Unreal만 연결한다.
- `detect`: 웹캠으로 손동작을 인식해 로컬 브리지의 `/cast`로 전송한다.
- `game`: Listen Server가 HP, 마나, 마법 슬롯, 공격 판정, 승패의 최종 권한을 가진다.
- 기존 `server/main.py`는 `client_bridge.main:app`을 불러오는 호환용이다.

## 실행 명령

프로젝트 루트 PowerShell에서 로컬 브리지를 실행한다.

```powershell
python -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```

가상환경 실행 파일을 직접 사용할 때는 PowerShell 경로 앞에 `./` 또는 `.\`가 필요하다.

```powershell
.\client_bridge\.venv\Scripts\python.exe -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```

detector만 직접 실행할 때:

```powershell
python detect\main.py
```

OpenCV 웹캠 창까지 표시하려면:

```powershell
python detect\main.py --show-window
```

중앙 매칭 서버는 8100 포트 사용을 권장한다.

```powershell
python -m uvicorn matchmaking_server.main:app --host 0.0.0.0 --port 8100
```

## detector와 카메라 UI

- `detect/main.py`는 인식한 손동작을 `http://127.0.0.1:8000/cast`로 보낸다.
- detector의 OpenCV 창은 기본적으로 숨겨져 있다.
- 로컬 브리지 카메라 경로는 `/camera`, `/camera/frame`, `/camera/latest.jpg`이다.
- Unreal UI에서는 Web Browser 위젯으로 `http://127.0.0.1:8000/camera`를 연다.
- 카메라 페이지가 요청되면 detector가 자동 실행되고, 카메라 요청이 일정 시간 끊기면 종료된다.
- Unreal 프로젝트에서 내장 `WebBrowserWidget` 플러그인을 활성화했다.
- PIE 폴링이 끊겼다가 다시 시작되면 이전 `/signal` 이벤트를 초기화해 지난 주문이 재실행되지 않도록 했다.

## 마법 ID와 비용

`ESpellID`:

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

비용은 `ST_SpellData` 구조체와 `DT_SpellData` Data Table에서 관리한다.

| ESpellID 및 Data Table 행 이름 | Cost |
|---|---:|
| FireBall | 2 |
| WindBlast | 2 |
| IceSpear | 3 |
| Lightning | 4 |
| Recovery | 4 |
| ManaDrain | 4 |
| Meteor | 7 |
| ArcaneBarrier | 6 |
| HeartSanctuary | 7 |
| ManaSurge | 3 |

중요: Data Table 행 이름은 `ESpellID` 내부 이름과 대소문자까지 정확히 같아야 한다. `GetSpellCost`에서는 `Enum → String → Name`으로 Row Name을 만들어 조회한다. Display Name을 사용하지 않는다.

## Unreal Blueprint 현재 구조

현재 작업 트리에 있는 핵심 자산:

```text
/Game/blueprints/BP_gamemode
/Game/blueprints/BP_playercontroller
/Game/blueprints/BP_SpellCastPlayerState
/Game/blueprints/ESpellID
/Game/blueprints/ST_SpellData
/Game/blueprints/DT_SpellData
```

`BP_gamemode`:

- Player Controller Class: `BP_playercontroller`
- Player State Class: `BP_SpellCastPlayerState`
- Default Pawn Class: 현재 사용하는 마녀 Pawn

`BP_playercontroller`:

- 로컬 컨트롤러만 로컬 브리지의 `/signal`을 폴링한다.
- 받은 주문 문자열을 `ESpellID`로 바꾼다.
- 소유 클라이언트가 Server RPC `Server_RequestCast(SpellID)`를 호출한다.
- Server RPC 안에서 자기 `BP_SpellCastPlayerState`를 가져온다.
- `CanCastSpell`이 참일 때만 `CommitCast`를 실행한다.

`BP_SpellCastPlayerState`:

- 플레이어별 HP, Mana, MaxMana, SpellCycle을 관리하는 위치다.
- Mana와 필요한 상태 변수는 RepNotify로 설정한다.
- 실제 상태 변경은 `Has Authority`가 참인 Listen Server에서만 수행한다.
- 서버에서 변경한 RepNotify 값은 Unreal 네트워크 복제로 클라이언트에 전달된다. Python/FastAPI는 이 복제에 관여하지 않는다.

## 주문 사용 판정

`SpellCycle`은 6개의 `ESpellID` 배열이며 인덱스 0, 1, 2가 현재 활성 슬롯이다.

`CanCastSpell(Spell)`:

```text
SpellCycle 길이가 3 이상인지 확인
→ Spell이 SpellCycle[0], [1], [2] 중 하나인지 확인
→ DT_SpellData에서 Cost 조회
→ Mana >= Cost 확인
→ 모든 조건을 AND하여 반환
```

`CommitCast(SpellID)`:

```text
Cost = GetSpellCost(SpellID)
→ Mana = Mana - Cost
→ SpellCycle에서 SpellID Remove Item
→ SpellCycle 맨 뒤에 SpellID Add
```

오늘 마나가 줄지 않던 원인은 `Get Data Table Row`에서 `Row Not Found`가 실행된 것이었다. Enum에서 만든 Row Name과 Data Table의 실제 행 이름을 정확히 맞춰 해결했다.

## 마나 자동 회복

`BP_SpellCastPlayerState`에서 서버만 반복 타이머를 실행한다.

```text
BeginPlay
→ Has Authority
→ 반복 Timer 시작
→ RegenerateMana
→ Mana < MaxMana이면 Set Mana = Clamp(Mana + 1, 0, MaxMana)
```

- 설정한 일정 시간마다 마나가 1 증가한다.
- `Mana`는 RepNotify이므로 서버 값이 각 클라이언트로 복제된다.
- PIE가 끝나 PlayerState가 제거되면 해당 타이머도 함께 사라진다.

## 2026-07-15 완료 지점

- 중앙 매칭 서버, 로컬 브리지, detector, Unreal Listen Server의 역할을 분리했다.
- 6자리 방 코드 기반 메모리 매칭 서버 코드를 만들었다.
- 로컬 브리지에 detector 자동 실행, 숨김 실행, 카메라 스트림 경로를 구현했다.
- `BP_SpellCastPlayerState`를 만들고 게임 상태를 Unreal 서버가 관리하도록 구성했다.
- 클라이언트의 주문 신호를 PlayerController Server RPC로 Listen Server에 전달하도록 구성했다.
- 활성 3슬롯 검사, Data Table 비용 조회, 마나 차감, 6슬롯 순환을 구현했다.
- Data Table Row Name 불일치로 마나가 줄지 않던 오류를 수정했다.
- 서버 권한의 마나 자동 회복을 구성했다.

## 아직 검증하거나 구현할 작업

- PIE에서 Listen Server 1개와 Client 1개를 띄워 각 플레이어의 `Mana`와 `SpellCycle` 복제를 실제 2인 환경에서 검증한다.
- `OnRep_Mana`, `OnRep_SpellCycle`에서 각 클라이언트 UI를 갱신한다.
- `ExecuteSpell` 및 각 주문의 실제 효과, 피해, 회복을 구현한다.
- HP, 피격, 승패 판정을 Listen Server 권한으로 구현한다.
- 6자리 매칭 결과를 Unreal의 Listen Server 생성 및 접속 흐름과 연결한다.

## Git 주의사항

- 현재 작업 트리에는 Unreal `.uasset`, 맵, UI, Python 코드 등 변경 파일이 매우 많다.
- 이 변경은 사용자가 Unreal Editor에서 작업한 내용이므로 임의로 되돌리거나 삭제하지 않는다.
- `git reset --hard`, `git checkout --` 같은 복구 명령을 함부로 실행하지 않는다.
- 다른 PC에서 이어서 작업하기 전에 Unreal Editor에서 Blueprint를 컴파일하고 모두 저장한다.
- 필요한 파일을 커밋한 뒤 원격 저장소에 push해야 다른 PC에서 받을 수 있다.
