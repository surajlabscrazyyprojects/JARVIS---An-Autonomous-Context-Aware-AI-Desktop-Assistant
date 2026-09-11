from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class DevelopmentToolAdapter:
    """Process-backed adapter; every operation reports observed process state."""

    def __init__(self, name: str, executable: str = "") -> None:
        self.name = name
        self.executable = executable or name.lower()
        self.process: Optional[subprocess.Popen] = None
        self.workspace: Optional[Path] = None
        self.last_instruction = ""

    def detect(self) -> Dict[str, Any]:
        path = shutil.which(self.executable)
        return {"name": self.name, "available": bool(path), "path": path or ""}

    def launch(self, workspace: str | Path | None = None) -> Dict[str, Any]:
        detected = self.detect()
        if not detected["available"]:
            return {"success": False, "verified": False, "error": f"{self.name} is unavailable"}
        self.workspace = Path(workspace).resolve() if workspace else None
        try:
            self.process = subprocess.Popen(
                [detected["path"]],
                cwd=str(self.workspace) if self.workspace else None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            return {"success": False, "verified": False, "error": str(exc)}
        return {"success": True, "verified": self.process.poll() is None, "pid": self.process.pid, "workspace": str(self.workspace or "")}

    def open_workspace(self, workspace: str | Path) -> Dict[str, Any]:
        path = Path(workspace).resolve()
        self.workspace = path
        verified = path.is_dir() and self.process is not None and self.process.poll() is None
        return {"success": verified, "verified": verified, "workspace": str(path)}

    def send_instruction(self, instruction: str) -> Dict[str, Any]:
        if not self.process or self.process.poll() is not None or self.process.stdin is None:
            return {"success": False, "verified": False, "error": f"{self.name} is not running"}
        try:
            self.process.stdin.write(instruction + os.linesep)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            return {"success": False, "verified": False, "error": str(exc)}
        self.last_instruction = instruction
        return {"success": True, "verified": False, "error": "Instruction delivered; acceptance requires adapter-specific confirmation"}

    def status(self) -> Dict[str, Any]:
        running = bool(self.process and self.process.poll() is None)
        return {"state": "running" if running else "stopped", "pid": self.process.pid if self.process else None, "workspace": str(self.workspace or "")}

    def stop(self) -> Dict[str, Any]:
        if not self.process or self.process.poll() is not None:
            return {"success": True, "verified": True, "state": "stopped"}
        self.process.terminate()
        self.process.wait(timeout=5)
        return {"success": True, "verified": self.process.poll() is not None, "state": "stopped"}
