import unittest

from jarvis.proactivity import ProactivityEngine
from jarvis.tools import DevelopmentToolAdapter, TaskPromptGenerator


class RuntimeAdapterTests(unittest.TestCase):
    def test_missing_development_tool_is_truthful(self) -> None:
        adapter = DevelopmentToolAdapter("OpenCode", "definitely-not-installed")
        result = adapter.launch()
        self.assertFalse(result["success"])
        self.assertFalse(result["verified"])
        self.assertIn("unavailable", result["error"])

    def test_prompt_marks_unavailable_context(self) -> None:
        prompt = TaskPromptGenerator().generate(
            "Build a website for this",
            {"browser": {}, "referenced_entity": {}},
            {"known": [], "observable": [], "unknown": ["design direction"]},
            "OpenCode",
        )
        self.assertIn("Unavailable", prompt)
        self.assertIn("Do not invent", prompt)

    def test_proactivity_is_silent_by_default_and_speaks_when_enabled(self) -> None:
        self.assertEqual("STAY_SILENT", ProactivityEngine().evaluate("TASK_COMPLETED", verified=True).action)
        engine = ProactivityEngine(enabled=True)
        self.assertEqual("SPEAK", engine.evaluate("TASK_COMPLETED", verified=True).action)
        self.assertEqual("STAY_SILENT", engine.evaluate("TASK_COMPLETED", verified=True).action)


if __name__ == "__main__":
    unittest.main()
