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
        bridge.latest_detection = bridge.DetectionStatus()
        bridge.latest_detection_at = 0.0
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
        self.assertEqual(signal["spell"], "FireBall")

    def test_first_signal_poll_after_pie_gap_clears_old_spell(self) -> None:
        bridge.latest_signal = bridge.LocalSignal(
            event_id=7, player_id="player1", gesture="ok", spell="ManaSurge"
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

    def test_live_detection_reports_gesture_and_progress(self) -> None:
        response = self.client.post(
            "/detection",
            json={
                "gesture": "fist",
                "confidence": 0.9,
                "held_frames": 5,
                "required_frames": 8,
                "detected": True,
            },
        )
        self.assertEqual(response.status_code, 200)

        status = self.client.get("/detection").json()
        self.assertEqual(status["gesture"], "fist")
        self.assertEqual(status["spell"], "FireBall")
        self.assertEqual(status["held_frames"], 5)
        self.assertEqual(status["progress"], 0.625)
        self.assertFalse(status["confirmed"])

    def test_live_detection_prefers_elapsed_time_for_progress(self) -> None:
        status = self.client.post(
            "/detection",
            json={
                "gesture": "peace",
                "confidence": 0.85,
                "held_frames": 6,
                "required_frames": 8,
                "held_seconds": 0.4,
                "required_seconds": 0.8,
                "detected": True,
            },
        ).json()
        self.assertEqual(status["progress"], 0.5)
        self.assertFalse(status["confirmed"])

    def test_live_detection_resets_when_not_detected_or_stale(self) -> None:
        self.client.post(
            "/detection",
            json={
                "gesture": "ok",
                "confidence": 0.8,
                "held_frames": 8,
                "required_frames": 8,
                "detected": True,
            },
        )
        cleared = self.client.post(
            "/detection",
            json={"detected": False, "required_frames": 8},
        ).json()
        self.assertEqual(cleared["gesture"], "none")
        self.assertEqual(cleared["progress"], 0.0)

        bridge.latest_detection_at = time.monotonic() - 1.0
        stale = self.client.get("/detection").json()
        self.assertFalse(stale["detected"])
        self.assertEqual(stale["held_frames"], 0)

    @patch("client_bridge.main.start_detector", return_value=True)
    def test_camera_page_starts_detector(self, start_detector) -> None:
        response = self.client.get("/camera")
        self.assertEqual(response.status_code, 200)
        start_detector.assert_called_once()


if __name__ == "__main__":
    unittest.main()
