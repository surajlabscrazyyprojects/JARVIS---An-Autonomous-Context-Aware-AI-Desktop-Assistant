"""Tests for the research workflow fast path (mocked browser)."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from jarvis.models import ToolResult
from jarvis.research.workflow import ResearchWorkflow, _tokens

YOUTUBE_LINKS = [
    {"href": "https://www.youtube.com/watch?v=abc123", "title": "Blender Tutorial for Beginners"},
    {"href": "https://www.youtube.com/watch?v=def456", "title": "Cooking With Gordon Ramsay"},
    {"href": "https://www.youtube.com/shorts/xyz", "title": "Blender Short"},
    {"href": "https://www.youtube.com/watch?v=ghi789", "title": "Blender 2026 Course"},
]


def _result(success=True, verified=True, output=None, error=None):
    return ToolResult(success=success, verified=verified, output=output or {}, error=error, duration_ms=1,
                      verification_method="mock")


class WorkflowFilterTests(unittest.TestCase):
    def test_filters_shorts_and_keeps_watch(self) -> None:
        wf = ResearchWorkflow(Mock())
        got = wf._filter_links(YOUTUBE_LINKS, "youtube")
        hrefs = [c.href for c in got]
        self.assertTrue(any("watch?v=abc123" in h for h in hrefs))
        self.assertTrue(any("watch?v=ghi789" in h for h in hrefs))
        self.assertNotIn("/shorts/", " ".join(hrefs))
        self.assertEqual(len(got), 3)

    def test_wikipedia_excludes_special(self) -> None:
        wf = ResearchWorkflow(Mock())
        links = [
            {"href": "https://en.wikipedia.org/wiki/Quantum_computing", "title": "Quantum computing"},
            {"href": "https://en.wikipedia.org/wiki/Help:Contents", "title": "Help"},
        ]
        got = wf._filter_links(links, "wikipedia")
        self.assertEqual(len(got), 1)
        self.assertIn("Quantum", got[0].title)


class WorkflowTests(unittest.TestCase):
    def test_build_queries_respects_constraints(self) -> None:
        wf = ResearchWorkflow(Mock())
        queries = wf._build_queries("blender", {"quality": True})
        self.assertEqual(queries[0], "blender")
        self.assertIn("best", queries[1])

    def test_rank_scores_relevant_first(self) -> None:
        wf = ResearchWorkflow(Mock())
        cands = [
            Mock(title="Cooking show", href="a"),
            Mock(title="Blender Tutorial for Beginners 2026", href="b"),
        ]
        ranked = wf._rank(cands, "blender tutorial for beginners", {"quality": True, "recency": True})
        self.assertEqual(ranked[0].href, "b")
        self.assertEqual(ranked[0].rank, 1)

    def test_groq_select_returns_none_when_unconfigured(self) -> None:
        wf = ResearchWorkflow(Mock(), groq=None)
        self.assertIsNone(wf._groq_select([], "q", {}))

    def test_research_full_flow_mocked(self) -> None:
        browser = Mock()
        links = _result(output={"links": YOUTUBE_LINKS})
        browser.navigate.return_value = _result(output={"url": "https://www.youtube.com/watch?v=abc123", "title": "Blender"})
        browser.extract_links.return_value = links
        wf = ResearchWorkflow(browser, groq=None)
        outcome = wf.research("blender tutorial for beginners", site_id="youtube")
        self.assertTrue(outcome.verified)
        self.assertEqual(outcome.selected.href, "https://www.youtube.com/watch?v=abc123")
        self.assertIn("YouTube", outcome.message)
        browser.navigate.assert_called()

    def test_research_no_results_is_honest(self) -> None:
        browser = Mock()
        browser.navigate.return_value = _result(output={"url": "https://www.youtube.com/results", "title": "Search"})
        browser.extract_links.return_value = _result(output={"links": []})
        wf = ResearchWorkflow(browser, groq=None)
        outcome = wf.research("zzzzz", site_id="youtube")
        self.assertFalse(outcome.success)
        self.assertIsNotNone(outcome.error)

    def test_playback_attempt(self) -> None:
        browser = Mock()
        browser.video_state.side_effect = [
            _result(output={"video": {"present": True, "paused": True}}),
            _result(output={"video": {"present": True, "paused": False}}),
        ]
        wf = ResearchWorkflow(browser)
        playing, note = wf._attempt_playback()
        self.assertTrue(playing)
        browser.press_key.assert_called_once_with("k")

    def test_rank_prefers_relevant_title_over_cooking(self) -> None:
        wf = ResearchWorkflow(Mock())
        cands = wf._filter_links(YOUTUBE_LINKS, "youtube")
        ranked = wf._rank(cands, "blender tutorial for beginners", {"quality": True})
        self.assertNotIn("Cooking", ranked[0].title)

    def test_build_note(self) -> None:
        wf = ResearchWorkflow(Mock())
        note = wf.build_note("fusion", "Summary text")
        self.assertIn("Fusion", note)
        self.assertIn("Summary text", note)

    def test_tokens_removes_stopwords(self) -> None:
        self.assertNotIn("the", _tokens("the best of the best"))


if __name__ == "__main__":
    unittest.main()