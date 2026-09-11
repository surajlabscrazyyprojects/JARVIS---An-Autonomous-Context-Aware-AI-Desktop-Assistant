from __future__ import annotations

from typing import Dict, Optional
from jarvis.fastcommand.parser import SITE_SEARCH_MAP, SITE_OPEN_MAP


class FastCommandRegistry:
    def __init__(self) -> None:
        self._site_search: Dict[str, str] = dict(SITE_SEARCH_MAP)
        self._site_open: Dict[str, str] = dict(SITE_OPEN_MAP)

    def search_url_for(self, site: str, query: str) -> Optional[str]:
        tmpl = self._site_search.get(site)
        if not tmpl:
            return None
        return tmpl.replace("{q}", query.replace(" ", "+"))

    def open_url_for(self, site: str) -> Optional[str]:
        return self._site_open.get(site)
