"""Tests for site registry, capability router, metrics, and lazy memory."""
from __future__ import annotations

import unittest

from jarvis.core import Metrics, get_capability_router
from jarvis.core.capability_router import CapabilityRouter
from jarvis.intent import IntentType
from jarvis.intent.sites import Site, get_site_registry, pick_default_site
from jarvis.research.workflow import _score_candidate, _tokens, ResearchOutcome, SearchCandidate


class SiteRegistryTests(unittest.TestCase):
    def test_build_search_url(self) -> None:
        registry = get_site_registry()
        url = registry.build_search_url("youtube", "blender tutorial")
        self.assertIn("youtube.com", url)
        self.assertIn("blender", url)

    def test_match_by_alias(self) -> None:
        registry = get_site_registry()
        site = registry.match("yt")
        self.assertIsNotNone(site)
        self.assertEqual(site.id, "youtube")

    def test_pick_default_site(self) -> None:
        self.assertEqual(pick_default_site(IntentType.RESEARCH_AND_OPEN), "youtube")
        self.assertEqual(pick_default_site("play me a video about cars"), "youtube")
        self.assertEqual(pick_default_site("what is the history of rome"), "wikipedia")

    def test_site_fields(self) -> None:
        site: Site = get_site_registry().match("youtube")  # type: ignore[assignment]
        self.assertEqual(site.id, "youtube")
        self.assertEqual(site.verify_domain, "youtube.com")


class CapabilityRouterTests(unittest.TestCase):
    def test_minimal_tool_set(self) -> None:
        router = get_capability_router()
        tools = router.for_intent(IntentType.OPEN_APPLICATION)
        self.assertIn("application.open", tools)
        self.assertNotIn("browser.navigate", tools)

    def test_research_gets_browser_and_playback(self) -> None:
        router = CapabilityRouter()
        tools = router.for_intent(IntentType.RESEARCH_AND_OPEN)
        self.assertIn("browser.search", tools)
        self.assertIn("browser.playback", tools)

    def test_singleton(self) -> None:
        self.assertIs(get_capability_router(), get_capability_router())


class MetricsTests(unittest.TestCase):
    def test_record_and_snapshot(self) -> None:
        m = Metrics()
        m.record("cat", 10.0, tokens=5)
        m.record("cat", 30.0, tokens=15)
        snap = m.snapshot()
        self.assertEqual(snap["cat"]["count"], 2)
        self.assertEqual(snap["cat"]["avg_ms"], 20.0)
        self.assertEqual(snap["cat"]["total_tokens"], 20)

    def test_timed_context(self) -> None:
        m = Metrics()
        with m.timed("x"):
            pass
        self.assertEqual(m.snapshot()["x"]["count"], 1)


class LazyMemoryTests(unittest.TestCase):
    def test_memory_not_required_for_smalltalk(self) -> None:
        from jarvis.brain.brain import Brain
        brain = Brain.__new__(Brain)
        self.assertFalse(brain._memory_required("how are you"))
        self.assertTrue(brain._memory_required("what is the task progress"))


class RankingTests(unittest.TestCase):
    def test_score_overlap(self) -> None:
        cand = SearchCandidate(title="Blender Tutorial for Beginners", href="http://x")
        low = SearchCandidate(title="Random Video About Cooking", href="http://y")
        terms = _tokens("blender tutorial for beginners")
        self.assertGreater(
            _score_candidate(cand, terms, {}),
            _score_candidate(low, terms, {}),
        )

    def test_outcome_defaults(self) -> None:
        o = ResearchOutcome(goal="g", site="youtube")
        self.assertFalse(o.success)
        self.assertEqual(o.message, "")


if __name__ == "__main__":
    unittest.main()