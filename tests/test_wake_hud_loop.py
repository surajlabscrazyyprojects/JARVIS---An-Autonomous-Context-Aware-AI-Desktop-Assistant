from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from jarvis.wake_service import WakeService, _is_wake
from run_jarvis_autostart import ActivationController


class _Process:
    def __init__(self, pid: int = 123) -> None:
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.returncode = -9


class WakeWordTests(unittest.TestCase):
    def test_wake_word_accepts_variants_and_rejects_substrings(self) -> None:
        self.assertTrue(_is_wake("Jarvis, wake up"))
        self.assertTrue(_is_wake("wake up jervis"))
        self.assertTrue(_is_wake("hey jarvis can you help me"))
        self.assertTrue(_is_wake("jarves"))
        self.assertFalse(_is_wake("my jarvison project"))
        self.assertFalse(_is_wake("jar of pickles"))
        self.assertFalse(_is_wake(""))

    def test_callback_pauses_only_after_successful_activation(self) -> None:
        wake = WakeService(on_wake_callback=lambda: False)
        wake._running = True
        wake._listening.set()
        wake._on_wake()
        self.assertTrue(wake.listening)

        wake.on_wake_callback = lambda: True
        wake._on_wake()
        self.assertFalse(wake.listening)


class ActivationLoopTests(unittest.TestCase):
    # The real HUD (jarvis-profile Chrome) may be open on this machine while
    # the suite runs — keep these unit tests hermetic.
    @patch("jarvis.hud_launcher._profile_process_running", return_value=False)
    def test_duplicate_activation_does_not_launch_another_hud(self, _prof) -> None:
        wake = WakeService()
        launch = Mock(return_value=_Process())
        controller = ActivationController(wake, launch_hud_fn=launch)
        controller._backend_ready = Mock(return_value=True)  # type: ignore[method-assign]
        with patch("run_jarvis_autostart.threading.Thread"), patch(
            "run_jarvis_autostart.verify_hud_started", return_value=True
        ):
            self.assertTrue(controller.activate())
            self.assertTrue(controller.activate())
        self.assertEqual(1, launch.call_count)

    @patch("jarvis.hud_launcher._profile_process_running", return_value=False)
    def test_failed_hud_launch_returns_false_to_keep_listener_active(self, _prof) -> None:
        wake = WakeService()
        controller = ActivationController(wake, launch_hud_fn=Mock(return_value=None))
        controller._backend_ready = Mock(return_value=True)  # type: ignore[method-assign]
        controller._stop_owned_backend = Mock()  # type: ignore[method-assign]
        self.assertFalse(controller.activate())
        self.assertEqual(2, controller.launch_hud_fn.call_count)

    @patch("jarvis.hud_launcher._profile_process_running", return_value=False)
    def test_unstable_hud_is_retried_then_reported_failed(self, _prof) -> None:
        wake = WakeService()
        launch = Mock(return_value=_Process())
        controller = ActivationController(wake, launch_hud_fn=launch)
        controller._backend_ready = Mock(return_value=True)  # type: ignore[method-assign]
        controller._stop_owned_backend = Mock()  # type: ignore[method-assign]
        with patch("run_jarvis_autostart.verify_hud_started", return_value=False):
            self.assertFalse(controller.activate())
        self.assertEqual(2, launch.call_count)


class HudLauncherTests(unittest.TestCase):
    def test_is_hud_running_tracks_launcher_process(self) -> None:
        from jarvis.hud_launcher import is_hud_running

        alive = _Process(pid=1)
        self.assertTrue(is_hud_running(alive))

        dead = _Process(pid=2)
        dead.returncode = 0
        with patch("jarvis.hud_launcher._profile_process_running", return_value=False):
            self.assertFalse(is_hud_running(dead))

    def test_is_hud_running_survives_chrome_handoff(self) -> None:
        from jarvis.hud_launcher import is_hud_running

        dead = _Process(pid=2)
        dead.returncode = 0
        with patch("jarvis.hud_launcher._profile_process_running", return_value=True):
            self.assertTrue(is_hud_running(dead))

    def test_verify_hud_started_rejects_immediate_crash(self) -> None:
        from jarvis.hud_launcher import verify_hud_started

        dead = _Process(pid=3)
        dead.returncode = 1
        with patch("jarvis.hud_launcher.is_hud_running", return_value=False):
            self.assertFalse(verify_hud_started(dead, grace_s=5.0))


class HudServerTests(unittest.TestCase):
    def test_hud_server_serves_entrypoint_over_http(self) -> None:
        from jarvis.hud_launcher import start_hud_server, stop_hud_server

        try:
            port = start_hud_server()
            self.assertIsNotNone(port)
            self.assertEqual(port, start_hud_server())  # idempotent

            import urllib.request

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/hologram_environment.html", timeout=10) as resp:
                body = resp.read(400).decode("utf-8", errors="replace")
            self.assertEqual(200, resp.status)
            self.assertIn("JARVIS Holographic Environment", body)
        finally:
            stop_hud_server()
            stop_hud_server()  # idempotent

    def test_hud_server_serves_module_with_js_mime(self) -> None:
        from jarvis.hud_launcher import start_hud_server, stop_hud_server

        try:
            port = start_hud_server()
            self.assertIsNotNone(port)

            import urllib.request

            req = urllib.request.Request(f"http://127.0.0.1:{port}/src/character/CharacterIntegration.js")
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.assertEqual(200, resp.status)
                self.assertEqual("application/javascript", resp.headers.get("Content-Type"))
                body = resp.read(200).decode("utf-8", errors="replace")
            self.assertIn("Character System Integration", body)
        finally:
            stop_hud_server()


if __name__ == "__main__":
    unittest.main()
