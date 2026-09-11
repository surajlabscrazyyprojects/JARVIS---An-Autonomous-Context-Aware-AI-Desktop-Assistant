"""
Unit tests for WorldState and main entry point initialization.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jarvis.observer import DesktopObserver, SystemState
from jarvis.runtime.resources import ResourceManager
from jarvis.world_state import WorldState, WorldStateManager


class TestWorldState(unittest.TestCase):
    def test_world_state_defaults_and_serialization(self) -> None:
        state = WorldState()
        d = state.to_dict()
        self.assertIn("timestamp", d)
        self.assertIn("active_window", d)
        self.assertEqual(d["active_window"], "")
        self.assertIn("system", d)
        self.assertEqual(d["system"]["inference_mode"], "normal")

    def test_world_state_manager_updates(self) -> None:
        with TemporaryDirectory() as tmpdir:
            obs = DesktopObserver()
            res = ResourceManager(Path(tmpdir))
            mgr = WorldStateManager(obs, res)

            mgr.update_vision(summary="Code editor showing main.py", screen_state_label="vscode")
            st = mgr.get()
            self.assertEqual(st.vision.summary, "Code editor showing main.py")
            self.assertEqual(st.vision.screen_state_label, "vscode")

            mgr.update_terminal(running=True, cwd=tmpdir, last_command="python --version", last_exit_code=0)
            st = mgr.get()
            self.assertEqual(st.terminal.last_command, "python --version")
            self.assertEqual(st.terminal.last_exit_code, 0)

            mgr.update_browser(active=True, url="http://localhost:8765", title="JARVIS HUD")
            st = mgr.get()
            self.assertTrue(st.browser.active)
            self.assertEqual(st.browser.url, "http://localhost:8765")

    def test_incremental_events_update_task_and_conversation_context(self) -> None:
        manager = WorldStateManager()
        events = []
        manager.subscribe(lambda event, payload: events.append((event, payload)))

        manager.apply_event("TRANSCRIPT_FINAL", {"text": "Build a website for this", "confidence": 0.94})
        manager.apply_event("TASK_EXECUTING", {"task_id": "task-1", "request_id": "req-1", "goal": "Build a website"})
        snapshot = manager.snapshot()

        self.assertEqual("Build a website for this", snapshot["conversation"]["recent_transcript"])
        self.assertEqual("executing", snapshot["task"]["status"])
        self.assertEqual("task-1", snapshot["task"]["task_id"])
        self.assertEqual(0.94, snapshot["sources"]["voice"]["confidence"])
        self.assertEqual(["TRANSCRIPT_FINAL", "TASK_EXECUTING"], [event for event, _ in events])


if __name__ == "__main__":
    unittest.main()
