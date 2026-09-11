from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.intent.sites import get_site_registry
from jarvis.models import ActionIntent, ActionResult, IntentType, ToolResult


def find_chrome() -> Optional[str]:
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Chromium\Application\chrome.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


class DirectActionExecutor:
    def __init__(
        self,
        computer: Any = None,
        browser: Any = None,
        vision: Any = None,
        discovery: Any = None,
        workflow: Any = None,
        terminal: Any = None,
        filesystem: Any = None,
    ) -> None:
        self.computer = computer
        self.browser = browser
        self.vision = vision
        self.discovery = discovery
        self.workflow = workflow
        self.terminal = terminal
        self.filesystem = filesystem
        self.registry = get_site_registry()

    def execute(self, intent: ActionIntent) -> ActionResult:
        kind = intent.intent
        if isinstance(kind, str):
            try:
                kind = IntentType(kind)
            except ValueError:
                pass

        if kind == IntentType.OPEN_APPLICATION:
            app_name = intent.app or intent.goal
            if not self.computer or not hasattr(self.computer, "open_app"):
                return ActionResult(success=False, verified=False, message="Computer control unavailable.")
            res: ToolResult = self.computer.open_app(app_name)
            if res.success and res.verified:
                msg = res.output.get("message", f"Opened {app_name}.")
                return ActionResult(success=True, verified=True, message=msg, data=res.output)
            err = res.error or "Failed to launch application"
            return ActionResult(success=False, verified=False, message=f"Could not open {app_name}: {err}", error=err)

        if kind == IntentType.OPEN_URL:
            url = intent.url or intent.goal
            opened = False
            try:
                opened = bool(webbrowser.open(url, new=2))
            except Exception:
                opened = False

            if opened:
                return ActionResult(success=True, verified=True, message="Opened in your default browser.", data={"url": url})

            chrome = find_chrome()
            if chrome:
                try:
                    subprocess.Popen([chrome, url])
                    return ActionResult(success=True, verified=True, message="Opened in Chrome.", data={"url": url})
                except Exception as exc:
                    return ActionResult(success=False, verified=False, message=f"Failed to launch Chrome: {exc}", error=str(exc))

            return ActionResult(success=False, verified=False, message="No suitable browser found to open URL.", error="no browser")

        if kind == IntentType.SITE_SEARCH:
            dest = intent.destination or "google"
            query = intent.query or intent.goal
            site = (self.workflow.registry.match(dest) if self.workflow and hasattr(self.workflow, "registry") else self.registry.match(dest))
            site_name = site.name if site else dest.capitalize()
            search_url = (self.workflow.registry.build_search_url(dest, query) if self.workflow and hasattr(self.workflow, "registry") else self.registry.build_search_url(dest, query))
            try:
                webbrowser.open(search_url, new=2)
                return ActionResult(success=True, verified=True, message=f"Searching on {site_name}.", data={"url": search_url})
            except Exception as exc:
                return ActionResult(success=False, verified=False, message=f"Search failed: {exc}", error=str(exc))

        if kind in (IntentType.RESEARCH, IntentType.RESEARCH_AND_OPEN):
            if not self.workflow:
                return ActionResult(success=False, verified=False, message="Research workflow unavailable.")
            dest = intent.destination or "youtube"
            query = intent.query or intent.goal
            outcome = self.workflow.research(query, site_id=dest, constraints=intent.constraints)
            if outcome.verified or outcome.success:
                return ActionResult(
                    success=True,
                    verified=outcome.verified,
                    message=outcome.message,
                    data={"opened_url": outcome.opened_url, "selected": outcome.selected},
                )
            return ActionResult(success=False, verified=False, message=outcome.error or "Research failed", error=outcome.error)

        if kind == IntentType.SCREEN_QUERY:
            if not self.vision or not hasattr(self.vision, "analyze"):
                return ActionResult(success=False, verified=False, message="Vision system unavailable.")
            ans = self.vision.analyze(intent.query or intent.goal)
            return ActionResult(success=True, verified=True, message=str(ans), data={"analysis": ans})

        if kind == IntentType.OPEN_FILE:
            file_path = intent.path or intent.goal
            if not os.path.isfile(file_path):
                return ActionResult(success=False, verified=False, message=f"File not found: {file_path}", error="not found")
            try:
                os.startfile(file_path)
                return ActionResult(success=True, verified=True, message=f"Opened file {file_path}.", data={"path": file_path})
            except Exception as exc:
                return ActionResult(success=False, verified=False, message=f"Failed to open file: {exc}", error=str(exc))

        if kind == IntentType.CREATE_NOTE:
            if not self.computer:
                return ActionResult(success=False, verified=False, message="Computer controller unavailable.")
            open_res = self.computer.open_app("notepad")
            note_content = intent.goal or ""
            type_res = self.computer.type_text(note_content)
            title = self.computer.active_window_title() if hasattr(self.computer, "active_window_title") else "Notepad"
            return ActionResult(
                success=True,
                verified=True,
                message=f"Created note in {title}.",
                data={"content": note_content, "title": title},
            )

        if kind == IntentType.TERMINAL_EXEC:
            if not self.terminal or not hasattr(self.terminal, "execute"):
                return ActionResult(success=False, verified=False, message="Terminal tool unavailable.", error="no terminal")
            cmd = intent.constraints.get("command") or intent.goal or ""
            # If python code snippet (e.g. print(...)) execute via temp file script
            if ("print(" in cmd or "\n" in cmd) and not cmd.startswith("python "):
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
                    f.write(cmd)
                    temp_path = f.name
                exec_cmd = f"python {temp_path}"
            else:
                exec_cmd = cmd

            res: ToolResult = self.terminal.execute(exec_cmd)
            stdout = res.output.get("stdout", "")
            stderr = res.output.get("stderr", "")
            msg = (stdout + "\n" + stderr).strip()
            if not msg and res.error:
                msg = res.error
            if res.success and res.verified:
                return ActionResult(success=True, verified=True, message=msg, data=res.output)
            return ActionResult(success=False, verified=False, message=msg or "Command execution failed.", error=res.error)

        return ActionResult(success=False, verified=False, message=f"Unhandled action intent: {kind}")
