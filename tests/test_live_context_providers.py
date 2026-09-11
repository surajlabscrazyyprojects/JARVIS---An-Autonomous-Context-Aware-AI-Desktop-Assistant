import unittest

from jarvis.observer import DesktopObserver
from jarvis.tools import BrowserTool
from jarvis.world_state import WorldStateManager


class LiveContextProviderTests(unittest.TestCase):
    def test_desktop_observer_returns_truthful_metadata_shape(self) -> None:
        info = DesktopObserver().get_active_window_info()
        self.assertIn("title", info)
        self.assertIn("application", info)
        self.assertIn(info["availability"], {"available", "unavailable"})
        self.assertGreaterEqual(info["confidence"], 0.0)

    def test_browser_provider_reports_unavailable_without_cdp(self) -> None:
        browser = BrowserTool(cdp_ports=(1,))
        result = browser.inspect_current_page()
        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("unavailable", result.error.lower())

    def test_browser_context_updates_world_state(self) -> None:
        world = WorldStateManager()
        world.apply_event("BROWSER_TAB_CHANGED", {
            "url": "https://maps.example.test/cafe",
            "title": "Cafe Listing",
            "text": "Cafe Listing\\nOpen now",
            "target_id": "tab-1",
        })
        self.assertEqual("Cafe Listing", world.snapshot()["browser"]["title"])
        self.assertEqual("tab-1", world.snapshot()["browser"]["target_id"])
        self.assertEqual("available", world.snapshot()["sources"]["browser"]["availability"])


if __name__ == "__main__":
    unittest.main()
