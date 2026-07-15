import time
import unittest

from fastapi.testclient import TestClient

from matchmaking_server.main import ROOM_TTL_SECONDS, app, rooms


class MatchmakingServerTest(unittest.TestCase):
    def setUp(self) -> None:
        rooms.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        rooms.clear()

    def test_create_join_start_and_close(self) -> None:
        created_response = self.client.post(
            "/rooms",
            json={"host_name": "host", "connection": "127.0.0.1:7777"},
        )
        self.assertEqual(created_response.status_code, 201)
        created = created_response.json()
        code = created["code"]
        token = created["host_token"]
        self.assertRegex(code, r"^\d{6}$")

        joined = self.client.post(
            f"/rooms/{code}/join", json={"player_name": "guest"}
        )
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.json()["connection"], "127.0.0.1:7777")

        started = self.client.post(
            f"/rooms/{code}/start", json={"host_token": token}
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "playing")

        closed = self.client.post(
            f"/rooms/{code}/close", json={"host_token": token}
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(self.client.get(f"/rooms/{code}").status_code, 404)

    def test_room_expires_without_heartbeat(self) -> None:
        created = self.client.post(
            "/rooms", json={"host_name": "host", "connection": "host:7777"}
        ).json()
        rooms[created["code"]].last_heartbeat_at = (
            time.monotonic() - ROOM_TTL_SECONDS
        )
        self.assertEqual(self.client.get(f"/rooms/{created['code']}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
