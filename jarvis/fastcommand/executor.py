from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.fastcommand.parser import (
    BROWSER_BACK, BROWSER_CLOSE_TAB, BROWSER_FORWARD, BROWSER_NEW_TAB,
    BROWSER_NEXT_TAB, BROWSER_PREV_TAB, BROWSER_REFRESH, ESCALATE,
    FILE_CREATE, FILE_FIND, GET_BRIGHTNESS, GET_VOLUME, MEDIA_NEXT,
    MEDIA_PAUSE, MEDIA_PLAY, MEDIA_PLAY_PAUSE, MEDIA_PREVIOUS, MEDIA_STOP,
    MISSING_PARAM, MUTE, OPEN_APP, OPEN_SITE, OPEN_URL, SEARCH_SITE,
    SET_BRIGHTNESS, SET_VOLUME, UNMUTE, FastCommand,
)
from jarvis.fastcommand.registry import FastCommandRegistry


@dataclass
class FastCommandResult:
    intent: str
    success: bool = True
    status: str = "VERIFIED"
    verified: bool = True
    response_key: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self):
        if not self.data and self.params:
            self.data = self.params


class FastCommandExecutor:
    def __init__(
        self,
        registry: Optional[FastCommandRegistry] = None,
        audio: Any = None,
        display: Any = None,
        media: Any = None,
        find_roots: Optional[List[Path]] = None,
    ) -> None:
        self.registry = registry or FastCommandRegistry()
        self.audio = audio
        self.display = display
        self.media = media
        self._find_roots = find_roots or []
        if not self._find_roots:
            home = Path.home()
            for folder in ["Documents", "Desktop", "Downloads", "Pictures", "Videos"]:
                p = home / folder
                if p.exists():
                    self._find_roots.append(p)
            if not self._find_roots:
                self._find_roots.append(home)

    def _resolve_location(self, loc: Optional[str]) -> Path:
        if not loc:
            return self._find_roots[0] if self._find_roots else Path.home()
        for root in self._find_roots:
            if root.name.lower() == loc.lower():
                return root
        # Try as absolute
        p = Path(loc).expanduser()
        if p.exists():
            return p
        return self._find_roots[0] if self._find_roots else Path.home()

    def execute(self, cmd: FastCommand) -> FastCommandResult:
        intent = cmd.intent

        if intent == SET_VOLUME:
            if self.audio and hasattr(self.audio, "set_volume"):
                r = self.audio.set_volume(cmd.value or 50)
                return FastCommandResult(
                    intent=SET_VOLUME,
                    success=r.success if hasattr(r, "success") else True,
                    status="VERIFIED",
                    verified=True,
                    response_key="volume_set",
                    data={"actual": cmd.value},
                )
            return FastCommandResult(intent=SET_VOLUME, success=False, verified=False, error="No audio adapter")

        if intent == GET_VOLUME:
            if self.audio and hasattr(self.audio, "get_volume"):
                r = self.audio.get_volume()
                vol = r.data.get("volume_percent") if hasattr(r, "data") else 0
                return FastCommandResult(
                    intent=GET_VOLUME,
                    success=True,
                    status="VERIFIED",
                    verified=True,
                    response_key="volume_got",
                    data={"volume": vol},
                )
            return FastCommandResult(intent=GET_VOLUME, success=False, verified=False, error="No audio adapter")

        if intent == SET_BRIGHTNESS:
            if self.display and hasattr(self.display, "set_brightness"):
                r = self.display.set_brightness(cmd.value or 50)
                if hasattr(r, "status") and r.status == "UNSUPPORTED":
                    return FastCommandResult(intent=SET_BRIGHTNESS, success=False, status="UNSUPPORTED", verified=False)
                return FastCommandResult(
                    intent=SET_BRIGHTNESS,
                    success=True,
                    status="VERIFIED",
                    verified=True,
                    response_key="brightness_set",
                    data={"brightness_percent": cmd.value},
                )
            return FastCommandResult(intent=SET_BRIGHTNESS, success=False, verified=False, status="UNSUPPORTED")

        if intent == GET_BRIGHTNESS:
            if self.display and hasattr(self.display, "get_brightness"):
                r = self.display.get_brightness()
                return FastCommandResult(
                    intent=GET_BRIGHTNESS,
                    success=True,
                    status="VERIFIED",
                    verified=True,
                    data={"brightness": r.data.get("brightness_percent") if hasattr(r, "data") else 0},
                )
            return FastCommandResult(intent=GET_BRIGHTNESS, success=False, verified=False)

        if intent == MUTE:
            if self.audio and hasattr(self.audio, "mute"):
                self.audio.mute()
            return FastCommandResult(intent=MUTE, success=True, verified=True, response_key="muted", data={})

        if intent == UNMUTE:
            if self.audio and hasattr(self.audio, "unmute"):
                self.audio.unmute()
            return FastCommandResult(intent=UNMUTE, success=True, verified=True, response_key="unmuted", data={})

        if intent in (MEDIA_PLAY, MEDIA_PAUSE, MEDIA_PLAY_PAUSE, MEDIA_NEXT, MEDIA_PREVIOUS, MEDIA_STOP):
            if self.media and hasattr(self.media, "send_key"):
                self.media.send_key(intent)
            return FastCommandResult(
                intent=intent, success=True, status="DELIVERED", verified=False, data={}
            )

        if intent in (BROWSER_REFRESH, BROWSER_BACK, BROWSER_FORWARD, BROWSER_NEW_TAB,
                      BROWSER_CLOSE_TAB, BROWSER_NEXT_TAB, BROWSER_PREV_TAB):
            return FastCommandResult(
                intent=intent, success=True, status="DELIVERED", verified=False, data={}
            )

        if intent == OPEN_APP:
            app = cmd.app or ""
            exe = shutil.which(app) or shutil.which(app.lower().replace(" ", ""))
            if not exe:
                return FastCommandResult(
                    intent=OPEN_APP, success=False, verified=False,
                    response_key="app_not_found", error=f"App not found: {app}"
                )
            try:
                subprocess.Popen([exe])
                return FastCommandResult(
                    intent=OPEN_APP, success=True, status="DELIVERED", verified=False, data={"app": app}
                )
            except Exception as exc:
                return FastCommandResult(
                    intent=OPEN_APP, success=False, verified=False, response_key="app_not_found", error=str(exc)
                )

        if intent == FILE_CREATE:
            root = self._resolve_location(cmd.location)
            name = cmd.name or "untitled"
            kind = cmd.file_kind or "file"
            if kind == "folder":
                target = root / name
                target.mkdir(parents=True, exist_ok=True)
                return FastCommandResult(
                    intent=FILE_CREATE, success=True, verified=True,
                    data={"path": str(target), "kind": "folder"}
                )
            else:
                ext = f".{kind}" if kind not in ("file", "text") else ".txt"
                if kind == "python":
                    ext = ".py"
                elif kind == "file" and "." in name:
                    ext = ""
                target = root / (name + ext)
                if not target.exists():
                    target.touch()
                return FastCommandResult(
                    intent=FILE_CREATE, success=True, verified=True,
                    data={"path": str(target), "kind": kind}
                )

        if intent == FILE_FIND:
            query = (cmd.query or "").lower()
            matches = []
            for root in self._find_roots:
                try:
                    for f in root.rglob("*"):
                        if query in f.name.lower():
                            matches.append(str(f))
                            if len(matches) >= 10:
                                break
                except Exception:
                    pass
            return FastCommandResult(
                intent=FILE_FIND, success=True, verified=True,
                data={"matches": matches}
            )

        return FastCommandResult(intent=intent, success=False, verified=False, error="Unknown intent")
