import unittest

from jarvis.runtime import Capability, CapabilityRegistry
from jarvis.tools import ToolOrchestrator, register_development_tools


class FakeTool:
    def __init__(self) -> None:
        self.value = 0

    def increment(self, amount: int = 1) -> bool:
        self.value += amount
        return True


class ToolOrchestratorTests(unittest.TestCase):
    def test_action_requires_post_action_verification(self) -> None:
        registry = CapabilityRegistry()
        registry.register(Capability("fake", "test tool"))
        tool = FakeTool()
        orchestrator = ToolOrchestrator(registry, {"fake": tool})

        result = orchestrator.execute(
            "fake",
            "increment",
            {"amount": 2},
            observe=lambda: tool.value,
            verify=lambda before, after: after == before + 2,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(2, result.after)

    def test_unknown_external_tools_are_explicitly_unavailable(self) -> None:
        registry = CapabilityRegistry()
        register_development_tools(registry, {"OpenCode": ("definitely-not-installed",)})

        result = ToolOrchestrator(registry).execute("OpenCode", "launch")

        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("unavailable", result.message)


if __name__ == "__main__":
    unittest.main()
