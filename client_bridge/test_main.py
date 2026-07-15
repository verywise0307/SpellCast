import unittest
from unittest.mock import patch
import time

from fastapi.testclient import TestClient

import client_bridge.main as bridge


class ClientBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        bridge.latest_signal = bridge.LocalSignal()
        bridge.next_event_id = 1
        bridge.last_signal_read_at = 0.0
        bridge.latest_camera_frame = None
        self.client = TestClient(bridge.app)

    def test_gesture_becomes_local_spell_signal(self) -> None:
        response = self.client.post(
            "/cast",
            json={
                "player_id": "player1",
                "gesture": "fist",
                "confidence": 0.9,
                "held_frames": 8,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["accepted"])

        signal = self.client.get("/signal").json()
        self.assertEqual(signal["event_id"], 1)
        self.assertEqual(signal["spell"], "fire_ball")

    def test_first_signal_poll_after_pie_gap_clears_old_spell(self) -> None:
        bridge.latest_signal = bridge.LocalSignal(
            event_id=7, player_id="player1", gesture="ok", spell="mana_surge"
        )
        bridge.next_event_id = 8
        bridge.last_signal_read_at = time.monotonic() - 3.0

        signal = self.client.get("/signal").json()
        self.assertEqual(signal["event_id"], 0)
        self.assertEqual(signal["spell"], "none")

    def test_camera_accepts_only_jpeg(self) -> None:
        rejected = self.client.post("/camera/frame", content=b"not jpeg")
        self.assertEqual(rejected.status_code, 400)

        jpeg = b"\xff\xd8test-frame\xff\xd9"
        accepted = self.client.post(
            "/camera/frame", content=jpeg, headers={"Content-Type": "image/jpeg"}
        )
        self.assertEqual(accepted.status_code, 204)
        frame = self.client.get("/camera/latest.jpg")
        self.assertEqual(frame.status_code, 200)
        self.assertEqual(frame.content, jpeg)

    @patch("client_bridge.main.start_detector", return_value=True)
    def test_camera_page_starts_detector(self, start_detector) -> None:
        response = self.client.get("/camera")
        self.assertEqual(response.status_code, 200)
        start_detector.assert_called_once()


if __name__ == "__main__":
    unittest.main()
