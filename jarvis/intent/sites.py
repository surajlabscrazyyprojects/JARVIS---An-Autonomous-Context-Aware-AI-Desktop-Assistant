from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional

from jarvis.models import IntentType


@dataclass
class Site:
    id: str
    name: str
    domain: str
    search_url_template: str
    verify_domain: str
    aliases: List[str]

    def build_search_url(self, query: str) -> str:
        encoded = urllib.parse.quote_plus(query)
        return self.search_url_template.format(query=encoded)


class SiteRegistry:
    def __init__(self) -> None:
        self._sites: Dict[str, Site] = {}
        self._alias_map: Dict[str, str] = {}
        self._register_defaults()

    def register(self, site: Site) -> None:
        self._sites[site.id.lower()] = site
        self._alias_map[site.id.lower()] = site.id.lower()
        for alias in site.aliases:
            self._alias_map[alias.lower()] = site.id.lower()

    def match(self, term: str) -> Optional[Site]:
        if not term:
            return None
        t = term.lower().strip()
        site_id = self._alias_map.get(t)
        if site_id and site_id in self._sites:
            return self._sites[site_id]
        for s in self._sites.values():
            if t in s.name.lower() or t in s.domain.lower():
                return s
        return None

    def build_search_url(self, site_id_or_alias: str, query: str) -> str:
        site = self.match(site_id_or_alias)
        if site:
            return site.build_search_url(query)
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.google.com/search?q={encoded}"

    def _register_defaults(self) -> None:
        self.register(
            Site(
                id="youtube",
                name="YouTube",
                domain="youtube.com",
                search_url_template="https://www.youtube.com/results?search_query={query}",
                verify_domain="youtube.com",
                aliases=["yt", "video", "videos", "tube"],
            )
        )
        self.register(
            Site(
                id="wikipedia",
                name="Wikipedia",
                domain="wikipedia.org",
                search_url_template="https://en.wikipedia.org/w/index.php?search={query}",
                verify_domain="wikipedia.org",
                aliases=["wiki", "encyclopedia"],
            )
        )
        self.register(
            Site(
                id="github",
                name="GitHub",
                domain="github.com",
                search_url_template="https://github.com/search?q={query}",
                verify_domain="github.com",
                aliases=["gh", "git", "repo", "repos"],
            )
        )
        self.register(
            Site(
                id="google",
                name="Google",
                domain="google.com",
                search_url_template="https://www.google.com/search?q={query}",
                verify_domain="google.com",
                aliases=["web", "search", "goog"],
            )
        )


_SITE_REGISTRY: Optional[SiteRegistry] = None


def get_site_registry() -> SiteRegistry:
    global _SITE_REGISTRY
    if _SITE_REGISTRY is None:
        _SITE_REGISTRY = SiteRegistry()
    return _SITE_REGISTRY


def pick_default_site(intent_or_phrase: IntentType | str) -> str:
    if isinstance(intent_or_phrase, IntentType):
        if intent_or_phrase in (IntentType.RESEARCH_AND_OPEN, IntentType.RESEARCH):
            return "youtube"
        return "google"
    phrase = str(intent_or_phrase).lower()
    if any(w in phrase for w in ["video", "watch", "play", "tutorial", "stream", "show me"]):
        return "youtube"
    if any(w in phrase for w in ["history", "what is", "who is", "define", "encyclopedia", "meaning"]):
        return "wikipedia"
    if any(w in phrase for w in ["code", "repo", "repository", "github", "library", "package"]):
        return "github"
    return "google"
