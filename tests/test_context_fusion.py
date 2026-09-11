import unittest

from jarvis.context import ContextFusionEngine
from jarvis.world_state import WorldStateManager


class ContextFusionTests(unittest.TestCase):
    def test_browser_reference_is_resolved_from_authorized_metadata(self) -> None:
        world = WorldStateManager()
        world.update_browser(True, "https://maps.example.test/cafe", "Cafe Listing")
        snapshot = ContextFusionEngine(world).snapshot("Build a website for this")

        self.assertEqual("build_website", snapshot.user_intent)
        self.assertEqual("browser_page", snapshot.referenced_entity["type"])
        self.assertEqual("Cafe Listing", snapshot.referenced_entity["title"])
        self.assertGreater(snapshot.confidence, 0.8)
        self.assertEqual("available", snapshot.sources["browser"]["availability"])

    def test_reference_is_not_fabricated_without_a_source(self) -> None:
        world = WorldStateManager()
        snapshot = ContextFusionEngine(world).snapshot("Open this")

        self.assertEqual("unresolved_reference", snapshot.referenced_entity["type"])
        self.assertLess(snapshot.referenced_entity["confidence"], 0.5)
        self.assertIn("current browser page", snapshot.unknown)


if __name__ == "__main__":
    unittest.main()
