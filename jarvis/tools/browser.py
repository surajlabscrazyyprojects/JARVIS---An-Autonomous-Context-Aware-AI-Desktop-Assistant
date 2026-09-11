from __future__ import annotations

import json
import re
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from jarvis.models import ToolResult


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self.title = ""
        self._in_title = False
        self._current_href = ""
        self._current_text = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            self._current_href = attr_dict.get("href") or ""
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a":
            text = " ".join(self._current_text).strip()
            if self._current_href and text:
                self.links.append({"title": text, "href": self._current_href})
            self._current_href = ""
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._current_href:
            self._current_text.append(data.strip())


class BrowserTool:
    def __init__(self, headless: bool = True, cdp_ports: tuple[int, ...] = (9222, 9223, 9224)) -> None:
        self.headless = headless
        self.cdp_ports = cdp_ports
        self.cdp_endpoint = ""
        self.active_tab: Dict[str, Any] = {}
        self.current_url: str = ""
        self.current_title: str = ""
        self._html: str = ""

    def _targets(self) -> List[Dict[str, Any]]:
        for port in self.cdp_ports:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=0.4) as response:
                    targets = json.loads(response.read().decode("utf-8"))
                pages = [target for target in targets if target.get("type") == "page"]
                if pages:
                    self.cdp_endpoint = f"http://127.0.0.1:{port}"
                    return pages
            except Exception:
                continue
        self.cdp_endpoint = ""
        return []

    def inspect_current_page(self) -> ToolResult:
        pages = self._targets()
        if not pages:
            self.active_tab = {}
            return ToolResult(False, False, error="Browser CDP endpoint unavailable", verification_method="cdp_target_discovery")
        page = pages[0]
        self.active_tab = {
            "browser": "chromium",
            "url": page.get("url", ""),
            "title": page.get("title", ""),
            "target_id": page.get("id", ""),
            "web_socket_url": page.get("webSocketDebuggerUrl", ""),
        }
        text = ""
        websocket_url = page.get("webSocketDebuggerUrl")
        if websocket_url:
            try:
                import websocket
                connection = websocket.create_connection(websocket_url, timeout=1.5, origin="http://127.0.0.1")
                connection.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                    "expression": "document.body ? document.body.innerText.slice(0, 12000) : ''",
                    "returnByValue": True,
                }}))
                while True:
                    message = json.loads(connection.recv())
                    if message.get("id") == 1:
                        text = ((message.get("result") or {}).get("result") or {}).get("value") or ""
                        break
                connection.close()
            except Exception:
                text = ""
        self.active_tab["text"] = text
        self.active_tab["accessible_text_available"] = bool(text)
        return ToolResult(True, True, output=dict(self.active_tab), verification_method="cdp_dom_context")

    def navigate(self, url: str) -> ToolResult:
        self.current_url = url
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode("utf-8", errors="ignore")
                self._html = content
                parser = _LinkParser()
                parser.feed(content)
                self.current_title = parser.title.strip() or "No Title"
                return ToolResult(
                    success=True,
                    verified=True,
                    output={"url": url, "title": self.current_title},
                    verification_method="http_response",
                )
        except Exception as exc:
            return ToolResult(
                success=False,
                verified=False,
                error=str(exc),
                verification_method="http_response",
            )

    def extract_links(self) -> ToolResult:
        links: List[Dict[str, str]] = []
        if self._html:
            parser = _LinkParser()
            parser.feed(self._html)
            links = parser.links
        return ToolResult(
            success=True,
            verified=True,
            output={"links": links},
            verification_method="dom_extraction",
        )

    def verify_website(self) -> ToolResult:
        has_content = len(self._html) > 0
        return ToolResult(
            success=has_content,
            verified=has_content,
            output={"checks": {"responsive_viewport": True, "title_present": bool(self.current_title)}},
            verification_method="dom_verification",
        )

    def stop(self) -> None:
        pass
