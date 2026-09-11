"""E2E probe for the REAL JARVIS backend over its real WebSocket (ws://127.0.0.1:8765).

Drives the true running jarvis.py backend with natural-language commands
(with and without a "wake word") and asserts REAL machine side effects
(notepad.exe actually launches, actually closes). Each command prints a
timestamped event trace (same schema the HUD uses).

Usage: python tools_e2e_probe.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WS_URL = "ws://127.0.0.1:8765"

FAILURES = []


def notepad_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq notepad.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        return "notepad.exe" in out.lower()
    except Exception:
        return False


def check(name: str, ok: bool, detail: str = ""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAILURES.append(name)


async def run_cmd(ws, text: str, tag: str, timeout: float = 120) -> list:
    req_id = f"REQ-{tag}"
    t0 = time.time()
    await ws.send(json.dumps({"type": "command", "text": text, "via_jarvis": True, "req_id": req_id}))
    events = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        ev = (round(time.time() - t0, 3), msg.get("type"), str(msg.get("text", ""))[:140],
              dict(msg.get("data") or {}) or None)
        events.append(ev)
        if msg.get("type") in ("done", "error"):
            break
    print(f"\n=== {tag}: {text!r} ===")
    for dt, typ, txt, data in events:
        print(f"  +{dt:>5.3f}s {typ:<16} {txt}")
    return events


async def main():
    async with websockets.connect(WS_URL, max_size=16 * 1024 * 1024) as ws:
        first = json.loads(await ws.recv())
        print("server welcome:", first.get("type"), first.get("server"), first.get("version"))

        # --- A. conversation, no wake word -------------------------------
        ev = await run_cmd(ws, "How are you?", "A1")
        final = [t for _, ty, t, _ in ev if ty in ("conversation",) and t]
        check("conversation reply received", bool(final) and not (final and final[-1].startswith("Planner error")), f"-> {final[-1] if final else 'none'}")

        # --- B. real action: Open Notepad (must NOT open a browser URL) ---
        ev = await run_cmd(ws, "Open Notepad.", "B1")
        opened_browser = any("https://" in t for _, ty, t, _ in ev if ty == "conversation")
        check("Open Notepad does NOT open browser URL", not opened_browser)
        await asyncio.sleep(2.0)
        check("notepad.exe actually running after Open Notepad.", notepad_running())

        # --- C. follow-up action with context ----------------------------
        ev = await run_cmd(ws, "Type hello.", "C1")
        typed = any("typed" in t.lower() for _, ty, t, _ in ev if ty == "conversation")
        check("Type hello executed", typed, f"-> {[t for _,ty,t,_ in ev if ty=='conversation']}")

        # --- D. interruption / cancellation ------------------------------
        ev = await run_cmd(ws, "stop", "D1", timeout=30)
        stopped = any(t.lower() in ("stopped, sir.", "stopped, sir") for _, ty, t, _ in ev if ty == "conversation")
        check("'stop' acknowledged with cancellation", stopped, f"-> {[t for _,ty,t,_ in ev if ty=='conversation']}")

        # --- E. close the app we opened, verify real close ---------------
        ev = await run_cmd(ws, "Close Notepad.", "E1")
        await asyncio.sleep(2.0)
        check("notepad.exe closed after Close Notepad.", not notepad_running())
        print("  closed summary:", [t for _, ty, t, _ in ev if ty == "conversation"])

        print(f"\nRESULT: {'ALL PASS' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
        sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=420))
    except TimeoutError:
        print("FATAL: suite timed out")
        sys.exit(2)
    except websockets.exceptions.ConnectionClosed as e:
        print("FATAL: connection closed unexpectedly:", e)
        sys.exit(3)
    except OSError as e:
        print("FATAL: cannot connect — is the backend running? (ws://127.0.0.1:8765)", e)
        sys.exit(4)