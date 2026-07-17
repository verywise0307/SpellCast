# SpellCast Codex 인수인계

최종 갱신: 2026-07-17

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

### 실시간 탐지 UI API

`detect/main.py`가 현재 손동작 상태를 로컬 브리지의 `POST /detection`으로 보내고,
Unreal은 `GET http://127.0.0.1:8000/detection`으로 읽는다.

```json
{
  "gesture": "fist",
  "confidence": 0.87,
  "held_frames": 5,
  "required_frames": 8,
  "held_seconds": 0.5,
  "required_seconds": 0.8,
  "detected": true,
  "spell": "FireBall",
  "progress": 0.625,
  "confirmed": false
}
```

- `progress`는 UMG Progress Bar의 `Percent`에 그대로 넣을 수 있다.
- detector 갱신이 0.5초 이상 끊기면 `/detection`은 미탐지 상태를 반환한다.
- 주문 확정은 같은 손동작을 연속 0.8초 유지했을 때 발생한다.
- 손동작이 사라지거나 다른 손동작으로 바뀌면 누적 상태가 초기화된다.
- 탐지, 상태 전송, 카메라 UI 전송 기본값은 모두 10FPS다.
- UI용 카메라 프레임은 중앙을 정사각형으로 자른 뒤 320×320 JPEG로 전송한다.
- YOLO 기본 장치는 Unreal과 GPU 경쟁을 줄이기 위해 `cpu`다. 필요하면 detector의 `--device` 옵션으로 바꾼다.
- `/camera` 페이지는 100ms마다 이미지를 갱신한다.

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

detector가 반환하는 `spell` 문자열도 같은 이름을 사용한다.

```text
fist       -> FireBall
palm       -> WindBlast
peace      -> IceSpear
rock       -> Lightning
like       -> Recovery
grip       -> ManaDrain
holy       -> Meteor
xsign      -> ArcaneBarrier
hand_heart -> HeartSanctuary
ok         -> ManaSurge
```

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

## 2026-07-16 파일로 확인된 작업

### Python 코드

- `client_bridge/main.py`에 실시간 손동작 상태용 `POST/GET /detection` API를 추가했다.
- `/detection`에 탐지 여부, gesture, ESpellID 형식 spell, 신뢰도, 누적 프레임, 누적 시간, 진행률, 확정 여부가 포함된다.
- detector 판정을 가변 추론 프레임 수 대신 같은 동작을 0.8초 유지하는 시간 기준으로 변경했다.
- detector 기본 탐지·상태·영상 전송 빈도를 10FPS로 제한했다.
- YOLO 기본 실행 장치를 CPU로 변경하고 `--device` 옵션을 추가했다.
- 카메라 UI 전송 이미지를 320×320으로 축소하고 브라우저 갱신 간격을 100ms로 변경했다.
- 탐지 결과의 모든 spell 문자열을 `ESpellID` 및 Data Table 행 이름과 같은 PascalCase로 통일했다.
- 관련 테스트 코드와 `client_bridge/README.md`, `detect/README.txt`, `GAME_MECHANICS.txt`를 갱신했다.
- Python 파일의 문법 검사는 통과했다.
- FastAPI 전체 테스트는 실행하지 못했다. 현재 `detect/.venv`와 `server/.venv`가 삭제된 Python 3.11 경로를 가리키며, 문서에 있는 `client_bridge/.venv`는 작업 폴더에 없다.

### UI 이미지와 Unreal 자산

- `/Game/UI/spellcard`에 10종 주문 카드 PNG 및 Unreal 임포트 자산이 존재한다.
- `/Game/UI/InGame`에 다음 HUD PNG와 임포트 자산이 존재한다.
  - `OpponentStatusFrame`
  - `PlayerStatusFrame`
  - `SpellSlotFrame`
  - `WebcamFrame`
  - `GesturePanel`
  - `CombatLogPanel`
  - `ArcaneCrosshair`
  - `DamageDirectionRight`
  - `InGameHUD_Atlas`
  - `circle`
- `/Game/UI/font`에 빛의 계승자 Regular/Bold 폰트 자산이 존재한다.
- `/Game/UI/WBP`에 `WBP_choosecards`, `WBP_holdingspell`, `WBP_webcam` 자산이 존재한다.
- 오늘 수정된 Unreal 바이너리 자산으로 `BP_SpellCastPlayerState`, `BP_playercontroller`, `DT_SpellData`, `WBP_webcam`, `battlemap`이 확인된다.
- `.uasset` 내부 Blueprint 노드 연결은 텍스트로 검사할 수 없으므로 위 자산의 세부 기능 완료 여부는 이 문서에서 단정하지 않는다.

## 아직 검증하거나 구현할 작업

- PIE에서 Listen Server 1개와 Client 1개를 띄워 각 플레이어의 `Mana`와 `SpellCycle` 복제를 실제 2인 환경에서 검증한다.
- `OnRep_Mana`, `OnRep_SpellCycle`에서 각 클라이언트 UI를 갱신한다.
- `ExecuteSpell` 및 각 주문의 실제 효과, 피해, 회복을 구현한다.
- HP, 피격, 승패 판정을 Listen Server 권한으로 구현한다.
- 6자리 매칭 결과를 Unreal의 Listen Server 생성 및 접속 흐름과 연결한다.
- `WBP_choosecards`의 30초 선택 종료, 6개 주문 제출, 위젯 종료 흐름을 PIE에서 검증한다.
- `BP_playercontroller`의 `Server_SetSpellCycle(ESpellID Array)`가 서버에서 배열 길이·중복을 검증하고 서버 PlayerState의 `SpellCycle`을 설정하는지 확인한다.
- 선택된 6개 주문의 순서 섞기가 서버 권한에서 수행되는지 확인한다.
- `/signal`과 `/detection` 완료 이벤트가 각각 별도 콜백으로 연결됐는지 확인한다.
- 인게임에서 detector CPU 실행과 10FPS 카메라 설정 적용 후 실제 게임 FPS를 측정한다.

## Git 주의사항

- 현재 작업 트리에는 Unreal `.uasset`, 맵, UI, Python 코드 등 변경 파일이 매우 많다.
- 이 변경은 사용자가 Unreal Editor에서 작업한 내용이므로 임의로 되돌리거나 삭제하지 않는다.
- `git reset --hard`, `git checkout --` 같은 복구 명령을 함부로 실행하지 않는다.
- 다른 PC에서 이어서 작업하기 전에 Unreal Editor에서 Blueprint를 컴파일하고 모두 저장한다.
- 필요한 파일을 커밋한 뒤 원격 저장소에 push해야 다른 PC에서 받을 수 있다.

## 2026-07-17 추가 인수인계: 로컬 실행과 화염구 작업 중단 지점

### 로컬 브리지와 웹캠 확인

- 이 PC에서는 처음에 전역 Python에 `uvicorn`이 없었고 `client_bridge/.venv`도 존재하지 않았다.
- 다음 순서로 가상환경을 만들어 로컬 브리지를 실행했다.

```powershell
python -m venv client_bridge\.venv
.\client_bridge\.venv\Scripts\python.exe -m pip install -r client_bridge\requirements.txt
.\client_bridge\.venv\Scripts\python.exe -m uvicorn client_bridge.main:app --host 127.0.0.1 --port 8000
```

- detector 전용 환경도 필요하다. 브리지는 `detect/.venv/Scripts/python.exe`가 있으면 그것으로 detector를 실행한다.

```powershell
python -m venv detect\.venv
.\detect\.venv\Scripts\python.exe -m pip install -r detect\requirements.txt
```

- `http://127.0.0.1:8000/camera`에서 처음 잠시 검은 화면이 나온 뒤 영상이 정상 표시되는 것을 확인했다.
- 검은 화면은 detector 시작, YOLO 모델 로딩, 카메라 초기화와 첫 JPEG 전송까지 걸리는 초기 지연이었다.
- 서버 로그에서 `POST /camera/frame` 204, `POST /detection` 200, `GET /camera/latest.jpg` 200이 반복되어 프레임과 탐지 상태 전송도 확인했다.
- 다음 수동 실행에서는 카메라 0번의 OpenCV 창이 정상 표시됐다.

```powershell
.\detect\.venv\Scripts\python.exe detect\main.py --show-window --camera 0
```

- 수동 detector와 브리지가 자동 실행한 detector를 동시에 켜면 웹캠 장치 점유가 충돌할 수 있으므로 동시에 실행하지 않는다.
- 간헐적인 `ConnectionResetError: [WinError 10054]`는 detector의 HTTP 전송 timeout이 0.1초로 짧아 연결을 먼저 끊을 때 생기는 부수 로그로 보인다. 영상은 계속 정상 전송됐다. 아직 코드는 수정하지 않았다.

### 화염구 작업 중인 Unreal 자산

아직 커밋하지 않은 사용자 작업이 존재한다. 특히 다음 신규 자산은 삭제하거나 되돌리지 않는다.

```text
/Game/blueprints/spells/BP_FireBall
/Game/blueprints/spells/M_FireBall
/Game/blueprints/spells/NS_fire
```

- `BP_FireBall.uasset`, `M_FireBall.uasset`, `NS_fire.uasset`이 신규 생성됐다.
- `NS_fire.uasset`은 약 16MB다.
- `BP_witch`, `BP_enemywitch`, `BP_playercontroller`가 수정됐다.
- `SpellCast.uproject`에서 `NiagaraFluids` 플러그인이 활성화됐다.
- 여러 UI 텍스처 및 주문 카드 `.uasset`도 Unreal Editor에 의해 수정 상태다. 바이너리 자산이므로 의도 없는 변경인지 에디터 재저장인지 다음 작업자가 확인한다.

### 화염구 구현 대화에서 정한 방향

- 실제 마법 실행 함수는 `BP_witch` 안에 있다.
- 따라서 `BP_witch`의 마법 실행 함수 내부에서는 `Self`가 곧 시전자 Pawn이다. 별도의 `CasterPawn`을 PlayerState에 저장하지 않는다.
- `BP_playercontroller`의 서버 RPC는 주문 유효성 검사와 `CommitCast`를 처리한 뒤, `Get Controlled Pawn -> Cast to BP_witch -> 마법 실행 함수` 순서로 호출하는 구성이 적절하다.
- 화염구 액터에는 충돌 컴포넌트, Niagara 또는 Mesh, `Projectile Movement Component`를 사용한다.
- 포물선 발사는 `Suggest Projectile Velocity Custom Arc`로 `StartPos`, `EndPos`, `LaunchVelocity`를 계산한 뒤 화염구를 Spawn하고 Projectile Movement의 Velocity를 설정하는 방향으로 논의했다.
- 시작 위치 초안:

```text
CasterLocation = Self.GetActorLocation
Direction = Normalize(TargetLocation - CasterLocation)
StartPos = CasterLocation + Direction * 100 + (0, 0, 100)
EndPos = TargetLocation + (0, 0, 80)
```

- 멀티플레이 목표는 Game State의 Player Array에서 시전자 PlayerState와 다른 PlayerState를 찾아 그 Pawn을 사용하는 방식을 논의했다.
- 혼자 PIE 테스트할 때 상대 PlayerState가 없으므로, 맵의 연습 표적 또는 `BP_enemywitch`에 `SpellTarget` Actor Tag를 붙이고 대체 목표로 찾는 방식을 논의했다.
- 권장 목표 선택 우선순위:

```text
1. 다른 플레이어의 Pawn
2. SpellTarget 태그가 붙은 연습 표적
3. 둘 다 없으면 발사하지 않음
```

- `TargetActor`는 화염구 실행 순간에만 필요한 값이므로 PlayerState에 영구 저장하기보다 마법 실행 함수의 지역 변수로 두는 방향이다.
- 장기적으로 상대 관계를 저장해야 한다면 Pawn 참조보다 `OpponentPlayerState`를 PlayerState에 저장하고 필요할 때 `Get Pawn`으로 현재 Pawn을 얻는 편이 리스폰에 안전하다.
- Projectile Spawn은 Listen Server 권한에서 수행하고 `BP_FireBall`의 `Replicates`, `Replicate Movement`를 활성화해야 한다.
- Spawn 시 `Owner`는 Controller 또는 시전자, `Instigator`는 `BP_witch Self`로 설정하고 충돌 시 `Other Actor != Get Instigator`를 확인해야 한다.

### 정확한 중단 지점 및 다음 작업

- 사용자가 화염구 Blueprint를 만들다가 중단했다. 위 로직이 실제 노드로 어디까지 연결됐는지는 `.uasset` 바이너리라 확인하지 못했다.
- 다음 작업자는 Unreal Editor에서 `BP_FireBall`, `BP_witch`, `BP_playercontroller`를 열어 컴파일 오류와 현재 노드 연결부터 확인한다.
- 우선 혼자 PIE에서 `SpellTarget` 표적으로 포물선 발사, 충돌, Destroy까지 검증한다.
- 그 다음 Listen Server + Client에서 양쪽 시전자 기준으로 반대편 Pawn을 목표로 잡는지 확인한다.
- 아직 피해량 적용, 폭발 효과, 서버 권한 피격 처리의 완료 여부는 확인되지 않았다.

## 2026-07-17 추가 인수인계: 화염구 비행과 손패 카드 사용 애니메이션

### 현재 Git 작업 상태

최신 커밋은 `fa27fbe 파이어볼에셋추가`이며 `main`, `origin/main`에 반영되어 있다. 이 커밋에는 화염구 Blueprint, 머티리얼, Niagara 시스템과 관련 Blueprint 변경 및 `NiagaraFluids` 플러그인 활성화가 포함된다.

커밋 이후 다음 Unreal 바이너리 자산이 다시 수정된 상태다. 사용자 작업이므로 삭제하거나 되돌리지 않는다.

```text
/Game/UI/WBP/WBP_holdingspell
/Game/blueprints/BP_witch
/Game/blueprints/spells/BP_FireBall
```

이 변경은 화염구의 비행 시간 조절과 손패 카드 사용 애니메이션 작업에 해당한다. `.uasset` 내부 노드 연결은 텍스트로 검증할 수 없으므로 Unreal Editor에서 컴파일 및 실제 실행으로 확인한다.

### 화염구 이동 구현의 현재 방향

- `Suggest Projectile Velocity Custom Arc`는 액터를 직접 이동시키지 않고 발사 속도 벡터만 계산한다.
- 계산 결과를 Spawn된 `BP_FireBall`의 `Projectile Movement Component -> Velocity`에 적용해야 한다.
- `Projectile Movement`의 `Updated Component`는 화염구의 Root Collision Component를 가리켜야 한다.
- `Simulation Enabled`, `Auto Activate`를 켜고 `Max Speed`는 계산 속도를 제한하지 않도록 충분히 크게 두거나 `0`으로 둔다.
- 월드 좌표로 계산한 속도를 넣을 때 `Velocity in Local Space`를 사용하지 않는다.

사용자가 목표 지점까지 정확히 3초 동안 비행하기를 원해 `Suggest Projectile Velocity Custom Arc` 대신 비행 시간을 기준으로 초기 속도를 직접 계산하는 방향으로 변경했다.

```text
FlightTime = 3.0
Delta = EndPos - StartPos

Velocity.X = Delta.X / FlightTime
Velocity.Y = Delta.Y / FlightTime
Velocity.Z = Delta.Z / FlightTime - 0.5 * GravityZ * GravityScale * FlightTime
```

Unreal 기본 월드 중력 `GravityZ = -980`일 때 Z 보정값은 다음과 같다.

```text
ZCorrection = 1470 * ProjectileGravityScale
```

현재 추천값은 낮은 포물선을 위한 다음 설정이다.

```text
Projectile Gravity Scale = 0.2
Flight Time = 3.0
Z Correction = 294

Velocity.X = Delta.X / 3
Velocity.Y = Delta.Y / 3
Velocity.Z = Delta.Z / 3 + 294
```

현재 Unreal 버전/노드 검색에서는 `Vector / Float`, `Scale Vector`, `Vector * Float`가 바로 노출되지 않았다. 따라서 Blueprint에서 `Break Vector`로 Delta를 X/Y/Z Float로 나누고 각 값을 `3.0`으로 나눈 뒤, Z에 보정값을 더하고 `Make Vector`로 다시 합치는 방식으로 안내했다.

중요: `Projectile Gravity Scale`만 낮추고 Z 보정값을 계속 `1470`으로 두면 화염구가 과도하게 위로 솟는다. 중력 스케일과 Z 보정값은 반드시 같은 비율로 맞춘다. 목표 전 충돌, Projectile Movement의 속도 제한, 다른 중력 설정이 있으면 실제 도착 시간이 3초보다 짧아지거나 달라질 수 있다.

### 손패 카드 사용 애니메이션

목표 UX는 다음과 같다.

```text
마법 사용
-> 사용한 카드가 위로 이동하며 투명해짐
-> 애니메이션 종료
-> 사용한 카드 제거 또는 슬롯 데이터 교체
-> 남은 카드가 빈자리를 채움
-> 새 카드가 마지막 슬롯으로 들어옴
```

카드 공통 Widget Blueprint인 `WBP_holdingspell`에 사용 애니메이션을 두는 방향이다. 같은 Widget Blueprint로 만들어진 카드 인스턴스는 모두 같은 애니메이션 정의를 가지며, 함수를 호출한 카드 인스턴스만 재생된다.

권장 애니메이션 예시:

```text
UseCardAnim1, 0.0초:
  Translation Y = 0
  Render Opacity = 1
  Scale = 1.0

UseCardAnim1, 약 0.4초:
  Translation Y = -250
  Render Opacity = 0
  Scale = 0.85
```

- 카드의 이미지, 텍스트 등 전체를 감싸는 `CardRoot` 위젯에 Render Transform과 Render Opacity 트랙을 적용한다.
- `WBP_holdingspell` 내부에 `PlayUseAnimation` 같은 Public 함수 또는 Custom Event를 만들고 그 안에서 `Play Animation(UseCardAnim1)`을 호출한다.
- 다른 Blueprint에서는 화면에 생성된 실제 `WBP_holdingspell Object Reference`를 저장한 뒤 `PlayUseAnimation`을 호출한다. Class Reference만으로는 인스턴스 애니메이션을 실행할 수 없다.
- 부모 손패 위젯에 Designer로 카드를 배치했다면 해당 카드의 `Is Variable`을 켠다.
- 여러 카드가 동적으로 생성된다면 카드 위젯 참조 배열에서 사용한 카드 Index를 찾아 그 인스턴스에만 `PlayUseAnimation`을 호출한다.

애니메이션 종료 처리에서 다음 오류가 발생했었다.

```text
Animation Finished (UseCardAnim1) 시그니처 오류:
선택된 함수/이벤트가 바인딩 가능하지 않습니다.
```

해결 방향:

- `Bind to Animation Finished`의 빨간 Delegate 핀에서 새 `Custom Event`를 직접 생성해 올바른 시그니처를 자동으로 맞춘다.
- 완료 이벤트는 입력값과 반환값이 없어야 하며 Pure 함수가 아니어야 한다.
- 함수에 `Delay` 같은 latent 노드를 넣지 않는다. 지연이 필요하면 Custom Event에서 처리한다.
- 해당 Unreal 버전에서 `Animation Finished (UseCardAnim1)` 전용 이벤트가 자동 제공되면 별도 Bind 없이 그 이벤트의 실행 핀에서 후속 로직을 연결한다.
- Bind는 `Event Construct` 등에서 한 번만 수행하고, 매 카드 사용 때 중복 Bind하지 않는다.

권장 부모/자식 책임 분리:

```text
WBP_holdingspell:
  PlayUseAnimation
  -> 입력 비활성화
  -> UseCardAnim1 재생
  -> 종료 시 CardUseAnimationFinished Dispatcher 호출

부모 손패 UI:
  Dispatcher 수신
  -> SpellCycle/UI 데이터 갱신
  -> 슬롯 Refresh
  -> 새 마지막 카드 진입 애니메이션 재생
```

`Delay 0.4 -> Remove From Parent`는 임시 확인용으로만 사용하고, 실제 구현에서는 Animation Finished 이벤트를 기준으로 카드 데이터와 UI를 갱신한다.

### Widget Image의 Texture2D 참조

Widget의 `Image`에 지정된 실제 Texture2D가 필요하면 다음 순서로 가져올 수 있다.

```text
Image Widget Reference
-> Get Brush
-> Break Slate Brush / Get Resource Object
-> Cast To Texture2D
```

버전에 따라 `Get Brush Resource as Texture2D`가 바로 제공될 수 있다. 반대로 Texture2D를 Image에 적용할 때는 `Set Brush From Texture`를 사용한다. 다만 주문 종류 판정은 표시용 Texture 비교가 아니라 `ESpellID` 또는 별도 `SpellType` 데이터로 처리한다.

### 다음 작업자가 Unreal Editor에서 확인할 순서

1. `BP_FireBall`, `BP_witch`, `WBP_holdingspell`을 열고 Compile 오류를 확인한다.
2. `BP_FireBall`의 Projectile Gravity Scale과 Z 보정값이 서로 일치하는지 확인한다. 현재 목표값은 `0.2`와 `294`다.
3. StartPos/EndPos를 Print String 또는 디버그 표시로 확인하고, 화염구가 장애물 없이 약 3초 후 EndPos에 도착하는지 측정한다.
4. 사용한 카드 인스턴스 하나만 `UseCardAnim1`을 재생하는지 확인한다.
5. Animation Finished가 한 번만 호출되고, 이후 손패 배열/슬롯 갱신 및 새 카드 표시가 실행되는지 확인한다.
6. 서버의 `SpellCycle` 갱신과 로컬 UI 애니메이션의 순서를 맞춘다. UI만 먼저 바꾸지 말고 서버에서 승인된 마법 사용 결과를 기준으로 최종 손패를 갱신한다.
7. Listen Server + Client에서 화염구 Spawn/Movement 복제와 각 플레이어 손패 UI가 서로 독립적으로 동작하는지 확인한다.

### 프로젝트 설정에서 발견한 주의점

- 프로젝트는 Unreal Engine `5.3` 연결이며 `HttpBlueprint`, `JsonBlueprintUtilities`, `WebBrowserWidget`, `NiagaraFluids`가 활성화되어 있다.
- `DefaultEngine.ini`의 `GameDefaultMap`, `EditorStartupMap`, `GlobalDefaultGameMode`는 아직 Third Person 템플릿 경로를 가리킨다. 실제 테스트가 `battlemap`과 `BP_gamemode`를 전제로 한다면 패키징/독립 실행 전에 Project Settings에서 기본 맵과 GameMode를 명시적으로 확인한다.
- Blueprint와 Widget의 세부 노드는 `.uasset` 바이너리라 저장소의 텍스트 검사만으로 완료 여부를 확정할 수 없다. 이 문서의 최근 Blueprint 항목은 사용자와의 구현 대화 및 변경 파일 목록을 기준으로 작성됐다.
