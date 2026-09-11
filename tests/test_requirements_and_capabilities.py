import unittest

from jarvis.context import ContextFusionEngine
from jarvis.reasoning import RequirementDiscoveryEngine
from jarvis.runtime import Capability, CapabilityRegistry
from jarvis.world_state import WorldStateManager


class RequirementsAndCapabilitiesTests(unittest.TestCase):
    def test_discovery_asks_high_value_questions_without_reasking_reference(self) -> None:
        world = WorldStateManager()
        world.update_browser(True, "https://maps.example.test/cafe", "Cafe Listing")
        discovery = RequirementDiscoveryEngine(ContextFusionEngine(world)).discover("Build a website for this")

        self.assertNotIn("Which business or page should I use as the reference?", discovery.questions)
        self.assertIn("design direction", discovery.unknown)
        self.assertLessEqual(len(discovery.questions), 3)
        self.assertIn("permission to create a project and start a development tool", discovery.required_confirmation)

    def test_capability_metadata_is_detectable_and_serializable(self) -> None:
        registry = CapabilityRegistry()
        registry.register(Capability("terminal", "Run development commands", executable="python"))
        detected = registry.detect("terminal")

        self.assertEqual("available", detected.availability)
        self.assertIn("terminal", registry.available())
        self.assertEqual("Run development commands", registry.snapshot()["terminal"]["description"])


if __name__ == "__main__":
    unittest.main()
