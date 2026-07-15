"""이전 실행 명령을 위한 호환 파일.

새 로컬 서버 코드는 client_bridge/main.py에 있다.
기존 `uvicorn main:app --app-dir server` 명령도 당분간 작동하게 연결만 한다.
새 작업에서는 `uvicorn client_bridge.main:app`을 사용하는 것을 권장한다.
"""

from client_bridge.main import app


__all__ = ["app"]
