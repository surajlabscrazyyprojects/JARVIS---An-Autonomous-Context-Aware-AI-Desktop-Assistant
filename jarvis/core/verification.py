from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VerificationReport:
    verified: bool
    evidence: str
    target: str
    method: str
    failure_reason: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "evidence": self.evidence,
            "target": self.target,
            "method": self.method,
            "failure_reason": self.failure_reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class VerificationEngine:
    """Anti-hallucination verification engine.
    
    Ensures JARVIS never claims an action succeeded without real evidence
    from the filesystem, process tree, window manager, or network stack.
    """

    @staticmethod
    def verify_filesystem(
        target_path: str | Path,
        must_exist: bool = True,
        is_directory: Optional[bool] = None,
        min_bytes: int = 0,
        content_contains: Optional[str] = None,
    ) -> VerificationReport:
        p = Path(target_path).resolve()
        method = "filesystem_stat"
        if not p.exists():
            if not must_exist:
                return VerificationReport(True, f"Path {p} does not exist as required", str(p), method)
            return VerificationReport(False, "", str(p), method, failure_reason=f"Path '{p}' does not exist.")

        if is_directory is True and not p.is_dir():
            return VerificationReport(False, "", str(p), method, failure_reason=f"Path '{p}' is not a directory.")
        if is_directory is False and p.is_dir():
            return VerificationReport(False, "", str(p), method, failure_reason=f"Path '{p}' is a directory, expected file.")

        if p.is_file():
            size = p.stat().st_size
            if size < min_bytes:
                return VerificationReport(False, "", str(p), method, failure_reason=f"File size {size} bytes is less than required {min_bytes} bytes.")
            if content_contains:
                try:
                    text = p.read_text("utf-8", errors="ignore")
                    if content_contains not in text:
                        return VerificationReport(False, "", str(p), method, failure_reason=f"File content does not contain required text '{content_contains[:50]}'.")
                except Exception as e:
                    return VerificationReport(False, "", str(p), method, failure_reason=f"Failed to read file: {e}")

        evidence = f"Verified path exists: {p} ({'dir' if p.is_dir() else f'{p.stat().st_size} bytes'})"
        return VerificationReport(True, evidence, str(p), method)

    @staticmethod
    def verify_process(process_name_or_pid: str | int, should_be_running: bool = True) -> VerificationReport:
        method = "process_inspection"
        target = str(process_name_or_pid)
        try:
            import psutil
            if isinstance(process_name_or_pid, int):
                is_running = psutil.pid_exists(process_name_or_pid)
                p_info = f"PID {process_name_or_pid}"
            else:
                name_low = process_name_or_pid.lower()
                matching = [
                    p for p in psutil.process_iter(["pid", "name"])
                    if name_low in (p.info.get("name") or "").lower()
                ]
                is_running = len(matching) > 0
                p_info = f"{len(matching)} matching processes for '{name_low}'"

            if is_running == should_be_running:
                evidence = f"Process {target} state verified: {'running' if is_running else 'stopped'} ({p_info})"
                return VerificationReport(True, evidence, target, method)
            else:
                reason = f"Process {target} expected running={should_be_running}, but got running={is_running}"
                return VerificationReport(False, "", target, method, failure_reason=reason)

        except Exception as exc:
            # Fallback to tasklist on Windows
            try:
                out = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {target}*"', shell=True, text=True, stderr=subprocess.DEVNULL)
                is_running = target.lower() in out.lower()
                if is_running == should_be_running:
                    return VerificationReport(True, f"Tasklist verified process {target}", target, method)
                return VerificationReport(False, "", target, method, failure_reason=f"Tasklist reported running={is_running}")
            except Exception:
                return VerificationReport(False, "", target, method, failure_reason=str(exc))

    @staticmethod
    def verify_window(title_pattern: str) -> VerificationReport:
        method = "window_manager"
        target = title_pattern
        try:
            import pygetwindow as gw
            titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
            low_pat = title_pattern.lower()
            matches = [t for t in titles if low_pat in t.lower()]
            if matches:
                evidence = f"Found window matching '{title_pattern}': '{matches[0]}'"
                return VerificationReport(True, evidence, target, method, metadata={"windows": matches})
            return VerificationReport(False, "", target, method, failure_reason=f"No window found matching title pattern '{title_pattern}'.")
        except Exception as exc:
            return VerificationReport(False, "", target, method, failure_reason=str(exc))

    @staticmethod
    def verify_url(url: str, timeout: float = 5.0, expected_status: int = 200) -> VerificationReport:
        method = "http_ping"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Verifier/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = response.getcode()
                if status == expected_status or (200 <= status < 400):
                    evidence = f"HTTP endpoint {url} responded with status {status}"
                    return VerificationReport(True, evidence, url, method, metadata={"status": status})
                return VerificationReport(False, "", url, method, failure_reason=f"HTTP status {status} != expected {expected_status}")
        except Exception as exc:
            return VerificationReport(False, "", url, method, failure_reason=f"Connection failed: {exc}")

    @staticmethod
    def verify_build_exit_code(exit_code: int, stdout: str = "", stderr: str = "") -> VerificationReport:
        method = "build_exit_code"
        if exit_code == 0:
            evidence = f"Build command completed with exit code 0. Output length: {len(stdout)} chars."
            return VerificationReport(True, evidence, "build_process", method)
        else:
            reason = f"Build failed with non-zero exit code {exit_code}. Stderr: {stderr[:300]}"
            return VerificationReport(False, "", "build_process", method, failure_reason=reason)

    @staticmethod
    def verify_email_draft(draft_data: Dict[str, Any]) -> VerificationReport:
        method = "email_draft_check"
        recipient = draft_data.get("recipient", "")
        subject = draft_data.get("subject", "")
        body = draft_data.get("body", "")

        if not recipient or "@" not in recipient:
            return VerificationReport(False, "", recipient, method, failure_reason="Invalid recipient email address.")
        if not subject:
            return VerificationReport(False, "", recipient, method, failure_reason="Email draft is missing a subject.")
        if not body or len(body.strip()) < 10:
            return VerificationReport(False, "", recipient, method, failure_reason="Email draft body is too short or empty.")

        evidence = f"Email draft verified for {recipient} with subject '{subject}' ({len(body)} chars)"
        return VerificationReport(True, evidence, recipient, method)
