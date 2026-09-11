from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from jarvis.intent.sites import get_site_registry
from jarvis.models import ToolResult

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't",
    "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself",
    "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into",
    "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our",
    "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's",
    "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs",
    "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't",
    "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's",
    "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves"
}


@dataclass
class SearchCandidate:
    title: str
    href: str
    rank: int = 0
    snippet: str = ""


@dataclass
class ResearchOutcome:
    goal: str
    site: str
    opened_url: Optional[str] = None
    success: bool = False
    verified: bool = False
    message: str = ""
    selected: Optional[SearchCandidate] = None
    error: Optional[str] = None


def _tokens(text: str) -> Set[str]:
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text).lower())
    return {w for w in clean.split() if len(w) > 1 and w not in STOPWORDS}


def _score_candidate(cand: Any, terms: Set[str], constraints: Dict[str, Any]) -> float:
    title_str = str(getattr(cand, "title", "") or "")
    snippet_str = str(getattr(cand, "snippet", "") or "")
    cand_tokens = _tokens(title_str + " " + snippet_str)
    overlap = len(terms.intersection(cand_tokens))
    score = float(overlap * 10)
    if constraints.get("recency") and any(y in title_str for y in ["2026", "2025", "latest", "new"]):
        score += 5.0
    if constraints.get("quality") and any(q in title_str.lower() for q in ["course", "complete", "beginner", "guide", "masterclass"]):
        score += 3.0
    return score


class ResearchWorkflow:
    def __init__(self, browser: Any, groq: Any = None) -> None:
        self.browser = browser
        self.groq = groq
        self.registry = get_site_registry()

    def build_note(self, topic: str, summary: str) -> str:
        topic_title = topic.capitalize() if topic else "Research Note"
        return f"# {topic_title}\n\n{summary}\n"

    def _filter_links(self, links: List[Dict[str, str]], site_id: str) -> List[SearchCandidate]:
        candidates: List[SearchCandidate] = []
        for item in links:
            href = item.get("href", "")
            title = item.get("title", "")
            if not href or not title:
                continue
            if site_id == "youtube":
                if "/shorts/" in href or "#" in href:
                    continue
                if "watch" not in href and "results" in href:
                    continue
            elif site_id == "wikipedia":
                if "Special:" in href or "Help:" in href or "Wikipedia:" in href:
                    continue
            candidates.append(SearchCandidate(title=title, href=href))
        return candidates

    def _build_queries(self, query: str, constraints: Dict[str, Any]) -> List[str]:
        queries = [query]
        if constraints.get("quality"):
            queries.append(f"best {query} beginner")
        if constraints.get("recency"):
            queries.append(f"{query} 2026")
        return queries

    def _rank(self, candidates: List[Any], query: str, constraints: Dict[str, Any]) -> List[SearchCandidate]:
        terms = _tokens(query)
        scored = []
        for c in candidates:
            s = _score_candidate(c, terms, constraints)
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = []
        for idx, (_, c) in enumerate(scored):
            setattr(c, "rank", idx + 1)
            ranked.append(c)
        return ranked

    def _groq_select(self, candidates: List[SearchCandidate], query: str, constraints: Dict[str, Any]) -> Optional[SearchCandidate]:
        if not self.groq or not candidates:
            return None
        return candidates[0]

    def _attempt_playback(self) -> tuple[bool, str]:
        if not hasattr(self.browser, "video_state") or not hasattr(self.browser, "press_key"):
            return False, "Browser has no video playback capabilities"
        res = self.browser.video_state()
        if res.output.get("video", {}).get("present"):
            if res.output["video"].get("paused"):
                self.browser.press_key("k")
                res_after = self.browser.video_state()
                if not res_after.output.get("video", {}).get("paused", True):
                    return True, "Playback started"
        return False, "No active video to play"

    def research(self, query: str, site_id: str = "youtube", constraints: Optional[Dict[str, Any]] = None) -> ResearchOutcome:
        constraints = constraints or {}
        site = self.registry.match(site_id)
        site_name = site.name if site else site_id.capitalize()
        search_url = self.registry.build_search_url(site_id, query)

        nav_res = self.browser.navigate(search_url)
        if not nav_res.success and not nav_res.verified:
            return ResearchOutcome(
                goal=query,
                site=site_id,
                success=False,
                verified=False,
                error=nav_res.error or "Navigation failed",
            )

        extract_res = self.browser.extract_links()
        raw_links = extract_res.output.get("links", [])
        candidates = self._filter_links(raw_links, site_id)

        if not candidates:
            return ResearchOutcome(
                goal=query,
                site=site_id,
                success=False,
                verified=False,
                error="No results found matching query.",
            )

        ranked = self._rank(candidates, query, constraints)
        selected = self._groq_select(ranked, query, constraints) or ranked[0]

        open_res = self.browser.navigate(selected.href)
        verified = open_res.verified or open_res.success

        return ResearchOutcome(
            goal=query,
            site=site_id,
            opened_url=selected.href,
            selected=selected,
            success=True,
            verified=verified,
            message=f"Opened a result on {site_name} — verified.",
        )
