import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jarvis.runtime import TaskStore


class TaskOwnershipTests(unittest.TestCase):
    def test_parent_task_persists_steps_and_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.json")
            task = store.create("Build a site", steps=[
                {"id": "requirements", "title": "Discover requirements"},
                {"id": "project", "title": "Create project"},
            ])
            store.transition(task["task_id"], "understanding")
            store.checkpoint(task["task_id"], 1)
            store.add_decision(task["task_id"], "style=premium")
            store.add_artifact(task["task_id"], {"path": "site"})

            restored = TaskStore(Path(directory) / "tasks.json").get(task["task_id"])
            self.assertEqual("requirements", restored["completed_steps"][0]["id"])
            self.assertEqual("project", restored["next_action"]["id"])
            self.assertEqual(["style=premium"], restored["decisions"])
            self.assertEqual("site", restored["artifacts"][0]["path"])

    def test_pause_and_blocked_are_persistable(self) -> None:
        with TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.json")
            task = store.create("Long task")
            store.transition(task["task_id"], "paused")
            store.transition(task["task_id"], "blocked")
            self.assertEqual("blocked", store.get(task["task_id"])["status"])


if __name__ == "__main__":
    unittest.main()
