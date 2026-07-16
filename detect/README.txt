SpellCast detector
==================

역할
----
- 각 플레이어 PC의 웹캠에서 HaGRIDv2 손동작을 인식한다.
- 중앙 매칭 서버에는 연결하지 않는다.
- 같은 PC의 client_bridge(127.0.0.1:8000)에만 연결한다.
- 손동작 결과는 POST /cast로 보낸다.
- 실시간 손동작과 누적 프레임은 POST /detection으로 보낸다.
- UI용 카메라 이미지는 POST /camera/frame으로 보낸다.

최초 설치
---------
python -m venv detect\.venv
detect\.venv\Scripts\python.exe -m pip install -r detect\requirements.txt

일반 실행
---------
보통은 Unreal의 카메라 UI가 client_bridge를 통해 detector를 자동 실행한다.
따라서 사용자가 직접 실행할 필요가 없다.

디버그 창을 보고 싶을 때만 다음 명령을 사용한다.

detect\.venv\Scripts\python.exe detect\main.py --image-size 320 --show-window

옵션
----
--camera 0          사용할 카메라 번호
--image-size 320    YOLO 입력 크기. 작을수록 빠르다.
--detect-fps 10     손동작 탐지 FPS. 기본값은 0.1초마다 한 번이다.
--hold-seconds 0.8  동일 손동작을 확정하기까지 유지할 시간
--device cpu        Unreal과 GPU 경쟁을 피하기 위해 기본 CPU에서 탐지한다.
--preview-fps 10    Unreal UI로 보낼 최대 FPS
--preview-size 320  UI로 보낼 정사각형 JPEG의 가로·세로 크기
--status-fps 10     손동작 UI 상태를 보낼 최대 FPS
--show-window       OpenCV 디버그 창 표시

종료
----
- 디버그 창이 있으면 Q 또는 Esc로 종료한다.
- 자동 실행된 detector는 PIE 종료 후 client_bridge가 종료한다.
