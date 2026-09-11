from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── Intent constants ──────────────────────────────────────────────────────────
SET_VOLUME = "SET_VOLUME"
GET_VOLUME = "GET_VOLUME"
SET_BRIGHTNESS = "SET_BRIGHTNESS"
GET_BRIGHTNESS = "GET_BRIGHTNESS"
MUTE = "MUTE"
UNMUTE = "UNMUTE"
MEDIA_PLAY = "MEDIA_PLAY"
MEDIA_PAUSE = "MEDIA_PAUSE"
MEDIA_PLAY_PAUSE = "MEDIA_PLAY_PAUSE"
MEDIA_NEXT = "MEDIA_NEXT"
MEDIA_PREVIOUS = "MEDIA_PREVIOUS"
MEDIA_STOP = "MEDIA_STOP"
BROWSER_REFRESH = "BROWSER_REFRESH"
BROWSER_BACK = "BROWSER_BACK"
BROWSER_FORWARD = "BROWSER_FORWARD"
BROWSER_NEW_TAB = "BROWSER_NEW_TAB"
BROWSER_CLOSE_TAB = "BROWSER_CLOSE_TAB"
BROWSER_NEXT_TAB = "BROWSER_NEXT_TAB"
BROWSER_PREV_TAB = "BROWSER_PREV_TAB"
OPEN_APP = "OPEN_APP"
OPEN_SITE = "OPEN_SITE"
OPEN_URL = "OPEN_URL"
SEARCH_SITE = "SEARCH_SITE"
FILE_CREATE = "FILE_CREATE"
FILE_FIND = "FILE_FIND"
MISSING_PARAM = "MISSING_PARAM"
ESCALATE = "ESCALATE"

WORD_TO_NUM: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}

APP_ALIASES: Dict[str, str] = {
    "visual studio code": "vscode", "vscode": "vscode", "vs code": "vscode",
    "chrome": "chrome", "google chrome": "chrome", "the chrome": "chrome",
    "notepad": "notepad", "notebook": "notepad",
    "calculator": "calculator", "calc": "calculator",
    "ae": "after effects", "after effects": "after effects",
    "premiere pro": "premiere pro", "premiere": "premiere pro",
    "spotify": "spotify",
    "whatsapp": "whatsapp",
    "firefox": "firefox", "edge": "edge",
    "word": "microsoft word", "excel": "excel", "powerpoint": "powerpoint",
    "file explorer": "file explorer", "explorer": "file explorer",
}

# Sites that can be "opened" (OPEN_SITE) or "searched" (SEARCH_SITE)
SITE_SEARCH_MAP: Dict[str, str] = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "github": "https://github.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
}

SITE_OPEN_MAP: Dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "wikipedia": "https://en.wikipedia.org",
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "spotify": "https://open.spotify.com",
    "whatsapp": "https://web.whatsapp.com",
}

SITE_ALIASES: Dict[str, str] = {
    "youtube": "youtube", "yt": "youtube",
    "google": "google",
    "wikipedia": "wikipedia", "wiki": "wikipedia",
    "github": "github", "gh": "github",
    "stackoverflow": "stackoverflow", "stack overflow": "stackoverflow",
}

ESCALATION_PATTERNS = [
    r"\b(best|top rated|recommend|which is better|compare|vs\b|explain|how to|what is|what\'s|describe|guide|tutorial on|learn about)\b",
    r"\b(top\s+\d+|ranking|ranked)\b",
]


@dataclass
class FastCommand:
    intent: str
    value: Optional[int] = None
    app: Optional[str] = None
    site: Optional[str] = None
    url: Optional[str] = None
    query: Optional[str] = None
    name: Optional[str] = None
    file_kind: Optional[str] = None
    location: Optional[str] = None
    missing: Optional[str] = None


def _extract_number(text: str) -> Optional[int]:
    """Extract numeric value from text (digits or word forms)."""
    m = re.search(r"\b(\d{1,3})\b", text)
    if m:
        return int(m.group(1))
    for word, val in WORD_TO_NUM.items():
        if re.search(rf"\b{word}\b", text):
            return val
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


class FastCommandParser:
    """Deterministic, zero-latency command parser."""

    def __init__(self, registry: Any = None) -> None:
        self.registry = registry

    def is_escalation(self, text: str) -> bool:
        normalized = _normalize(text)
        t = normalized.lower()
        # Fast-command intents are never escalations
        if self._is_site_search(t):
            return False
        # Volume/brightness queries are never escalations
        if re.search(r"\b(volume|brightness)\b", t):
            return False
        # Check escalation patterns
        for pat in ESCALATION_PATTERNS:
            if re.search(pat, t):
                return True
        return False

    def _is_site_search(self, t: str) -> bool:
        return bool(re.search(r"\b(pe|par|on|search|dhoondo)\b", t) and
                    any(site in t for site in SITE_SEARCH_MAP))

    def parse(self, text: str) -> Optional[FastCommand]:
        if not text:
            return None
        normalized = _normalize(text)
        t = normalized.lower()

        # ── Escalations check ─────────────────────────────────────────────────
        if self.is_escalation(t):
            return FastCommand(ESCALATE)

        # ── URLs ─────────────────────────────────────────────────────────────
        url_match = re.search(
            r"(https?://\S+|www\.\S+\.\w+(?:/\S*)?|\b[a-z0-9-]+\.(com|org|io|net|dev|co|in)(?:/\S*)?)",
            t,
        )
        if url_match and re.match(r"^(open|go to)\b", t):
            raw = url_match.group(0)
            url = raw if raw.startswith("http") else ("https://" + raw)
            return FastCommand(OPEN_URL, url=url)

        # ── Site search ("youtube pe X search kar") ──────────────────────────
        cmd = self._try_site_search(t)
        if cmd:
            return cmd

        # ── Volume ───────────────────────────────────────────────────────────
        # Handle mute/unmute before volume parsing ("volume mute"/"volume on").
        if re.search(r"\b(unmute|mute\s+off|sound\s+on|volume\s+on)\b", t):
            return FastCommand(UNMUTE)
        if re.search(r"\b(mute|aawaz\s+band|sound\s+band)\b", t):
            return FastCommand(MUTE)

        if re.search(r"\bvolume\b", t):
            if re.search(r"\b(kya hai|what is|current|batao|check)\b", t):
                return FastCommand(GET_VOLUME)
            n = _extract_number(t)
            if n is not None:
                return FastCommand(SET_VOLUME, value=n)
            if re.search(r"^\s*volume(\s+(kar|set|to))?\s*$", t):
                return FastCommand(MISSING_PARAM, missing="volume_value")
            return FastCommand(MISSING_PARAM, missing="volume_value")

        # ── Brightness ───────────────────────────────────────────────────────
        if re.search(r"\bbrightness\b", t):
            if re.search(r"\b(kya hai|what is|check)\b", t):
                return FastCommand(GET_BRIGHTNESS)
            n = _extract_number(t)
            if n is not None:
                return FastCommand(SET_BRIGHTNESS, value=n)
            return FastCommand(MISSING_PARAM, missing="brightness_value")

        # Tab-specific phrases must win over media words ("next tab", "tab band kar").
        if re.search(r"\b(tab|page\s+refresh|reload)\b", t):
            browser = self._try_browser(t)
            if browser:
                return browser

        # ── Media ─────────────────────────────────────────────────────────────
        media = self._try_media(t)
        if media:
            return media

        # ── Browser ──────────────────────────────────────────────────────────
        browser = self._try_browser(t)
        if browser:
            return browser

        # ── File create / find ────────────────────────────────────────────────
        file_cmd = self._try_file(normalized)
        if file_cmd:
            return file_cmd

        # ── Open app / site ───────────────────────────────────────────────────
        open_cmd = self._try_open(t)
        if open_cmd:
            return open_cmd

        return None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _try_site_search(self, t: str) -> Optional[FastCommand]:
        """Match: 'youtube pe X search kar' | 'search X on youtube' | 'youtube par X dhoondo'"""
        # Pattern A: <site> pe/par <query> search kar/dhoondo
        m = re.match(
            r"^(?P<site>[a-z]+)\s+(?:pe|par)\s+(?P<query>.+?)\s+(?:search\s+(?:kar|karo|karna)|dhoondo)$",
            t,
        )
        if not m:
            # Pattern B: <query> <site> pe search kar
            m = re.match(
                r"^(?P<query>.+?)\s+(?P<site>[a-z]+)\s+(?:pe|par)\s+(?:search\s+(?:kar|karo|karna)|dhoondo)$",
                t,
            )
        if not m:
            # Pattern C: search <query> on <site>
            m = re.match(r"^search\s+(?P<query>.+?)\s+on\s+(?P<site>[a-z]+)$", t)
        if not m:
            # Pattern D: <site> pe/par <query> dhoondo (direct without search)
            m = re.match(
                r"^(?P<site>[a-z]+)\s+(?:pe|par)\s+(?P<query>.+?)\s+dhoondo$",
                t,
            )
        if not m:
            # Pattern E: <site> pe/par <query> search karo
            m = re.match(
                r"^(?P<site>[a-z]+)\s+(?:pe|par)\s+(?P<query>.+?)\s+(?:search\s+karo)$",
                t,
            )
        if m:
            site_raw = m.group("site").strip()
            query = m.group("query").strip()
            site = SITE_ALIASES.get(site_raw, site_raw)
            if site in SITE_SEARCH_MAP:
                return FastCommand(SEARCH_SITE, site=site, query=query)
        # Pattern F: <site> pe github pe fastapi search kar
        m = re.match(
            r"^(?P<site>[a-z]+)\s+pe\s+(?P<query>.+?)\s+search\s+(?:kar|karo)$",
            t,
        )
        if m:
            site_raw = m.group("site").strip()
            query = m.group("query").strip()
            site = SITE_ALIASES.get(site_raw, site_raw)
            if site in SITE_SEARCH_MAP:
                return FastCommand(SEARCH_SITE, site=site, query=query)
        return None

    def _try_media(self, t: str) -> Optional[FastCommand]:
        if re.search(r"\b(play\s*pause|pause\s*play|toggle)\b", t):
            return FastCommand(MEDIA_PLAY_PAUSE)
        if re.search(r"\b(play|resume|continue|bajao|play\s+(?:the\s+)?(?:music|song))\b", t):
            return FastCommand(MEDIA_PLAY)
        if re.search(r"\b(pause|thama\s+do|pause\s+(?:kar|karo))\b", t):
            return FastCommand(MEDIA_PAUSE)
        if re.search(r"\b(next|skip|aage\s+badhao|next\s+(?:kar|song|track)|song\s+change)\b", t):
            return FastCommand(MEDIA_NEXT)
        if re.search(r"\b(previous|prev|pichla\s+song|previous\s+(?:kar|song|track)|back\s+song)\b", t):
            return FastCommand(MEDIA_PREVIOUS)
        if re.search(r"\b(stop|rok|rok\s+do|band\s+(?:kar|karo)|stop\s+(?:kar|the\s+music))\b", t):
            return FastCommand(MEDIA_STOP)
        return None

    def _try_browser(self, t: str) -> Optional[FastCommand]:
        if re.search(r"\b(refresh|reload)(?:\s+(?:page|kar|the\s+page|kar))?\b", t):
            return FastCommand(BROWSER_REFRESH)
        if re.search(r"\b(page\s+refresh\s+kar|reload\s+kar)\b", t):
            return FastCommand(BROWSER_REFRESH)
        if re.search(r"\b(go\s+)?forward(?:\s+ja)?\b", t):
            return FastCommand(BROWSER_FORWARD)
        if re.search(r"\b(go\s+)?back|peeche\s+ja|wapis\s+ja\b", t):
            return FastCommand(BROWSER_BACK)
        if re.search(r"\b(new\s+tab|naya\s+tab|tab\s+kholo|open\s+new\s+tab)\b", t):
            return FastCommand(BROWSER_NEW_TAB)
        if re.search(r"\b(close\s+(?:this\s+)?tab|tab\s+band\s+kar)\b", t):
            return FastCommand(BROWSER_CLOSE_TAB)
        if re.search(r"\b(next\s+tab|tab\s+change)\b", t):
            return FastCommand(BROWSER_NEXT_TAB)
        if re.search(r"\b(previous\s+tab|pichla\s+tab|last\s+tab)\b", t):
            return FastCommand(BROWSER_PREV_TAB)
        return None

    def _try_file(self, t: str) -> Optional[FastCommand]:
        # FILE_FIND
        find_m = re.match(
            r"^(?:find|dhoondo|search\s+for|where\s+is)\s+(?:my\s+)?(?P<query>.+)$",
            t,
        )
        if find_m:
            query = find_m.group("query").strip()
            # Exclude open targets
            return FastCommand(FILE_FIND, query=query)

        # FILE_CREATE — missing name
        if re.match(r"^create\s+(?:a\s+)?(?:file|folder)\s*$", t):
            return FastCommand(MISSING_PARAM, missing="file_info")

        # FILE_CREATE — "create folder Projects [in Documents]"
        folder_m = re.match(
            r"^create\s+(?:a\s+)?folder\s+(?P<name>[^\s]+(?:\s+[^\s]+)*?)(?:\s+in\s+(?P<loc>.+))?$",
            t,
        )
        if folder_m:
            name = folder_m.group("name").strip()
            loc = folder_m.group("loc")
            if loc:
                loc = loc.strip()
            return FastCommand(FILE_CREATE, name=name, file_kind="folder", location=loc)

        # FILE_CREATE — "create [a] <kind> file named <name> [in <loc>]"
        named_m = re.match(
            r"^create\s+(?:a\s+)?(?P<kind>[a-z]+)\s+file\s+named\s+(?P<name>.+?)(?:\s+in\s+(?P<loc>.+))?$",
            t,
        )
        if named_m:
            kind = named_m.group("kind").strip()
            name = named_m.group("name").strip()
            loc = named_m.group("loc")
            if loc:
                loc = loc.strip()
            return FastCommand(FILE_CREATE, name=name, file_kind=kind, location=loc)

        # FILE_CREATE — "create file hello.txt [in Documents]"
        file_m = re.match(
            r"^create\s+(?:a\s+)?file\s+(?P<name>[^\s]+(?:\s+[^\s]+)*?)(?:\s+in\s+(?P<loc>.+))?$",
            t,
        )
        if file_m:
            name = file_m.group("name").strip()
            loc = file_m.group("loc")
            if loc:
                loc = loc.strip()
            return FastCommand(FILE_CREATE, name=name, file_kind="file", location=loc)

        return None

    def _try_open(self, t: str) -> Optional[FastCommand]:
        open_kw = r"^(?:open(?:\s+the)?|kholo|khol|chalao|launch)\s+"
        # Missing target
        if re.match(r"^(?:open|kholo|khol|open\s+kar|launch|search|search\s+kar)\s*$", t):
            return FastCommand(MISSING_PARAM, missing="target")

        # Check known apps (longest-match first)
        for alias in sorted(APP_ALIASES.keys(), key=len, reverse=True):
            m = re.search(rf"(?:^|\s){re.escape(alias)}(?:\s|$)", t)
            if m:
                # Also confirm an open trigger is present
                if re.search(r"\b(open|kholo|khol|chalao|launch)\b", t) or t == alias:
                    app = APP_ALIASES[alias]
                    return FastCommand(OPEN_APP, app=app)

        # Check known sites
        for alias in sorted(SITE_ALIASES.keys(), key=len, reverse=True):
            m = re.search(rf"(?:^|\s){re.escape(alias)}(?:\s|$)", t)
            if m and re.search(r"\b(open|kholo|khol|chalao|launch)\b", t):
                site = SITE_ALIASES[alias]
                return FastCommand(OPEN_SITE, site=site)

        return None
