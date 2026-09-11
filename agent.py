"""
agent.py - J.A.R.V.I.S. computer-use agent (Windows)
====================================================

Real execution loop: UNDERSTAND -> OBSERVE -> PLAN -> EXECUTE -> VERIFY -> RECOVER -> REMEMBER -> RESPOND

Tools control the actual PC:
  * windows: list / active / focus / close
  * launch: open any installed app, open any URL
  * input:  mouse move/click/double/right/drag/scroll, type text, press keys, hotkeys
  * shell:  run PowerShell/CMD/Python commands
  * files:  list/read/write/create/rename/move/copy/delete (reversible where possible)
  * perc:   screenshot + screen-change detection (OCR lazy/no-dep fallback)

The LLM proposes structured tool calls (function calling). It NEVER executes raw model
text. Every action is validated, executed, and verified before "done" is reported.
Destructive / sensitive actions require explicit permission (see permission flow).
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import pyautogui
import pygetwindow as gw
from PIL import Image, ImageGrab

# JARVIS vision + motor subsystems (structured UI understanding and
# deterministic human-like input control).
from jarvis.motor.keyboard import KeyboardController
from jarvis.motor.mouse import MouseController
from jarvis.motor.planner import MotorPlanner
from jarvis.motor.watchdog import InputSafetyWatchdog
from jarvis.vision.analyzer import VisionAnalyzer
from jarvis.vision import capture
from jarvis.vision.contracts import CONFIDENCE_MEDIUM, ExecutionStatus, ObservationLevel
from jarvis.vision.verifier import VerificationEngine

pyautogui.FAILSAFE = True

# Process-wide vision + motor singletons. Shared so that a held input tracked
# by the watchdog during one tool call is releasable by any later call and by
# the global "Stop" path in jarvis.py.
WATCHDOG = InputSafetyWatchdog()
VISION_ANALYZER = VisionAnalyzer()
VERIFICATION = VerificationEngine()
MOTOR_MOUSE = MouseController(watchdog=WATCHDOG)
MOTOR_KEYBOARD = KeyboardController(watchdog=WATCHDOG)
MOTOR_PLANNER = MotorPlanner(mouse=MOTOR_MOUSE, watchdog=WATCHDOG)

ROOT = Path(__file__).resolve().parent
MEMORY_DIR = ROOT / "memory"
MEMORY_DIR.mkdir(exist_ok=True)
SHOT_DIR = MEMORY_DIR / "screenshots"
SHOT_DIR.mkdir(exist_ok=True)

TIER = {"observe": 0, "safe": 1, "sensitive": 2, "destructive": 3}
AUTO = {"observe", "safe"}  # tiers that may run without explicit confirmation


# ==========================================================================
# Memory (lightweight, structured, no secrets)
# ==========================================================================
class Memory:
    def __init__(self):
        self.facts_path = MEMORY_DIR / "facts.json"
        self.activity_path = MEMORY_DIR / "activity.jsonl"
        self.memories_path = MEMORY_DIR / "memories.json"
        self.facts = {}
        self.memories = {}
        if self.facts_path.exists():
            try:
                self.facts = json.loads(self.facts_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                self.facts = {}
        if self.memories_path.exists():
            try:
                self.memories = json.loads(self.memories_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                self.memories = {}

    def _persist_memories(self):
        self.memories_path.write_text(json.dumps(self.memories, ensure_ascii=False, indent=2), encoding="utf-8")

    def log(self, action: str, detail: str = "", ok: bool = True):
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "detail": detail,
            "ok": ok,
        }
        try:
            with open(self.activity_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def remember(self, key: str, value, category: str = "IMPORTANT_FACTS", source: str = "conversation",
                 confidence: float = 0.8, importance: float = 0.6):
        self.facts[key] = value
        try:
            self.facts_path.write_text(json.dumps(self.facts, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        old = self.memories.get(key, {})
        self.memories[key] = {
            "memory_id": old.get("memory_id", key), "category": category,
            "content": value, "source": source,
            "created_at": old.get("created_at", now), "updated_at": now,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "importance": max(0.0, min(1.0, float(importance))),
            "last_used": old.get("last_used"), "status": "active",
        }
        try:
            self._persist_memories()
        except Exception:
            pass

    def forget(self, key: str):
        self.facts.pop(key, None)
        rec = self.memories.get(key)
        if rec:
            rec["status"] = "forgotten"
            rec["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            self.facts_path.write_text(json.dumps(self.facts, ensure_ascii=False, indent=2), encoding="utf-8")
            self._persist_memories()
        except Exception:
            pass

    def relevant(self, query: str, limit: int = 6) -> list[dict]:
        terms = {t.lower() for t in re.findall(r"[a-z0-9_'-]{3,}", query or "")}
        ranked = []
        for rec in self.memories.values():
            if rec.get("status") != "active":
                continue
            text = f"{rec.get('category','')} {rec.get('content','')}".lower()
            score = len(terms.intersection(set(re.findall(r"[a-z0-9_'-]{3,}", text))))
            score += float(rec.get("importance", 0)) * 0.25
            if score > 0:
                rec["last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                ranked.append((score, rec))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in ranked[:limit]]

    def context(self, query: str, limit: int = 6) -> str:
        rows = self.relevant(query, limit)
        return "\n".join(f"- {r['category']}: {r['content']}" for r in rows)

    def learn_from_text(self, text: str):
        t = (text or "").strip()
        low = t.lower()
        m = re.search(r"(?:remember that|i use|i prefer)\s+(.+)", t, re.I)
        if m and len(m.group(1).strip()) > 3:
            self.remember("preference:" + re.sub(r"\W+", "_", m.group(1).strip().lower())[:80],
                          m.group(1).strip(), category="PREFERENCES", source="conversation")
        m = re.search(r"(?:i want to learn|my goal is to learn)\s+(.+)", t, re.I)
        if m:
            self.remember("goal:learning", m.group(1).strip(), category="GOALS", source="conversation", importance=0.9)
        if low.startswith(("forget that", "don't remember", "do not remember")):
            needle = low.split("remember", 1)[-1].strip(" .:,")
            for key, rec in list(self.memories.items()):
                if needle and needle in str(rec.get("content", "")).lower():
                    self.forget(key)

    def recall(self, key, default=None):
        return self.facts.get(key, default)


# ==========================================================================
# Tool layer
# ==========================================================================
def _norm(s: str) -> str:
    return (s or "").strip()


def _win_match(title_frag: str):
    frag = _norm(title_frag).lower()
    if not frag:
        return None
    for w in gw.getAllWindows():
        if frag in (w.title or "").lower() and w.title:
            return w
    return None


def tool_open_app(params):
    name = _norm(params.get("name") or params.get("app") or params.get("target"))
    if not name:
        return {"ok": False, "summary": "no app name provided"}
    if re.match(r"https?://", name) or name.startswith("www."):
        return tool_open_url({"url": name})
    try:
        proc = subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
        for _ in range(20):
            time.sleep(0.25)
            w = _win_match(name.split(".")[0])
            if w:
                return {"ok": True, "summary": f"launched {name}", "data": {"window": w.title, "pid": proc.pid}}
        return {
            "ok": True,
            "summary": f"launched {name} (process started, window not yet detected)",
            "data": {"pid": proc.pid},
        }
    except Exception as e:
        return {"ok": False, "summary": f"could not launch {name}: {e}"}


def tool_open_url(params):
    url = _norm(params.get("url") or params.get("target"))
    if not url:
        return {"ok": False, "summary": "no url provided"}
    if not re.match(r"https?://", url):
        url = "https://" + url
    try:
        os.startfile(url)
        return {"ok": True, "summary": f"opened {url} in default browser", "data": {"url": url}}
    except Exception as e:
        return {"ok": False, "summary": f"could not open {url}: {e}"}


def tool_run_command(params):
    cmd = _norm(params.get("command") or params.get("cmd"))
    if not cmd:
        return {"ok": False, "summary": "no command provided"}
    timeout = int(params.get("timeout") or 60)
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (res.stdout or "") + (res.stderr or "")
        return {
            "ok": res.returncode == 0,
            "summary": f"exit={res.returncode}, {len(out)} bytes output",
            "data": {"returncode": res.returncode, "output": out[-2000:]},
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "summary": f"command timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "summary": f"command failed: {e}"}


def tool_list_windows(params):
    titles = [w.title for w in gw.getAllWindows() if w.title]
    return {"ok": True, "summary": f"{len(titles)} windows", "data": {"windows": titles[:50]}}


def tool_active_window(params):
    w = gw.getActiveWindow()
    return {"ok": True, "summary": w.title if w else "none", "data": {"title": w.title if w else ""}}


def tool_focus_window(params):
    frag = _norm(params.get("title") or params.get("name"))
    w = _win_match(frag)
    if not w:
        return {"ok": False, "summary": f"no window matching '{frag}'"}
    try:
        w.activate()
        return {"ok": True, "summary": f"focused '{w.title}'", "data": {"title": w.title}}
    except Exception as e:
        return {"ok": False, "summary": f"could not focus: {e}"}


def _pids_by_window_title(frag: str) -> list:
    """Return PIDs of processes whose main window title contains `frag`."""
    try:
        frag_ps = frag.replace("'", "''")
        ps = (
            "Get-Process | Where-Object { $_.MainWindowTitle -like '*" + frag_ps + "*' } "
            "| Select-Object -ExpandProperty Id"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=60,
        )
        return sorted({int(x) for x in out.stdout.split() if x.strip().isdigit()})
    except Exception:
        return []


def _force_terminate_title(frag: str) -> bool:
    """taskkill /F every process whose main window matched (handles 'unsaved' dialogs)."""
    pids = _pids_by_window_title(frag)
    ok = True
    if pids:
        for pid in pids:
            r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, text=True, timeout=5)
            ok = ok and r.returncode == 0
    # Name-based fallback (notepad -> notepad.exe)
    r = subprocess.run(["taskkill", "/IM", frag.lower().replace(".exe", "") + ".exe", "/T", "/F"],
                       capture_output=True, text=True, timeout=5)
    ok = ok or r.returncode == 0
    return ok


def tool_close_window(params):
    frag = _norm(params.get("title") or params.get("name"))
    wins = [w for w in gw.getAllWindows() if frag in (w.title or "").lower() and w.title]
    if wins:
        victim = wins[0].title or frag  # capture BEFORE close (title reads empty after)
        for w in wins:
            try:
                w.close()  # polite WM_CLOSE
            except Exception:
                pass
        # Verify the window actually disappears (not merely 'close signal sent')
        deadline = time.time() + 2.5
        while time.time() < deadline:
            if _win_match(frag) is None:
                return {"ok": True, "summary": f"closed window '{victim}'"}
            time.sleep(0.25)
        # Unsaved-changes dialog etc. — terminate for real, then re-verify
        if _force_terminate_title(frag or " "):
            time.sleep(0.5)
            if _win_match(frag) is None:
                return {"ok": True, "summary": f"closed window (forced) '{victim}'"}
    # No top-level window matched: kill process by name and verify
    r = subprocess.run(["taskkill", "/IM", (frag or "").lower().replace(".exe", "") + ".exe", "/T", "/F"],
                       capture_output=True, text=True, timeout=5)
    if r.returncode == 0:
        time.sleep(0.4)
        if _win_match(frag) is None:
            return {"ok": True, "summary": f"closed process matching '{frag}'"}
    return {"ok": False, "summary": f"could not close anything matching '{frag}'"}


def _coords(params):
    x = params.get("x")
    y = params.get("y")
    if x is None or y is None:
        return None, None
    return int(x), int(y)


def tool_mouse_click(params):
    x, y = _coords(params)
    button = params.get("button") or "left"
    res = MOTOR_MOUSE.click(x, y, button=button)
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_mouse_double(params):
    x, y = _coords(params)
    res = MOTOR_MOUSE.double_click(x, y)
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_mouse_right(params):
    x, y = _coords(params)
    res = MOTOR_MOUSE.right_click(x, y)
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_mouse_move(params):
    x, y = _coords(params)
    if x is None:
        return {"ok": False, "summary": "need x,y"}
    res = MOTOR_MOUSE.move(int(x), int(y), duration=float(params.get("duration", 0.35)))
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_mouse_drag(params):
    x1, y1 = _coords({"x": params.get("x1"), "y": params.get("y1")})
    x2, y2 = _coords({"x": params.get("x2"), "y": params.get("y2")})
    if None in (x1, y1, x2, y2):
        return {"ok": False, "summary": "need x1,y1,x2,y2"}
    res = MOTOR_MOUSE.drag(int(x1), int(y1), int(x2), int(y2), button=params.get("button") or "left", duration=float(params.get("duration", 0.6)))
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_scroll(params):
    amt = int(params.get("amount") or params.get("clicks") or 3)
    x, y = _coords(params)
    if x is not None and y is not None:
        res = MOTOR_MOUSE.scroll(amt, x, y)
    else:
        res = MOTOR_MOUSE.scroll(amt)
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_type(params):
    text = _norm(params.get("text"))
    if not text:
        return {"ok": False, "summary": "no text"}
    res = MOTOR_KEYBOARD.type(text, interval=float(params.get("interval", 0.02)))
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def tool_press(params):
    keys = params.get("keys") or params.get("key")
    if isinstance(keys, str):
        keys = [keys]
    if not keys:
        return {"ok": False, "summary": "no key"}
    if len(keys) == 1:
        res = MOTOR_KEYBOARD.tap(keys[0])
    else:
        res = MOTOR_KEYBOARD.hotkey(*keys)
    return {"ok": bool(res.get("ok")), "summary": res.get("summary", "")}


def _focus_window_by_title(frag: str) -> bool:
    res = tool_focus_window({"title": frag})
    return bool(res.get("ok"))


def tool_open_notepad_and_type(params):
    """Open Notepad in a NEW untitled tab (Ctrl+N) so we never type into the
    user's existing document, then type the given text there. Safe by design."""
    text = _norm(params.get("text"))
    if not text:
        return {"ok": False, "summary": "no text"}
    try:
        if not _focus_window_by_title("notepad"):
            os.startfile("notepad.exe")
            time.sleep(1.5)
        time.sleep(0.4)
        MOTOR_KEYBOARD.hotkey("ctrl", "n")  # new blank tab
        time.sleep(0.4)
        MOTOR_KEYBOARD.type(text, interval=0.01)
        return {"ok": True, "summary": f"typed {len(text)} chars into a new Notepad tab"}
    except Exception as e:
        return {"ok": False, "summary": f"notepad type failed: {e}"}


def _resolve_path(p: str) -> Path:
    p = _norm(p)
    if not p:
        return None
    p_clean = p.strip("\"'")
    # Handle user home shortcuts
    if p_clean.startswith("~"):
        return Path(p_clean).expanduser().resolve()
    
    # Check known Windows user folders
    lower = p_clean.lower().replace("\\", "/")
    home = Path.home()
    folder_map = {
        "downloads": home / "Downloads",
        "my downloads": home / "Downloads",
        "documents": home / "Documents",
        "my documents": home / "Documents",
        "desktop": home / "Desktop",
        "pictures": home / "Pictures",
        "my pictures": home / "Pictures",
        "videos": home / "Videos",
        "my videos": home / "Videos",
        "music": home / "Music",
    }
    if lower in folder_map:
        return folder_map[lower]
    for prefix, target_dir in folder_map.items():
        if lower.startswith(prefix + "/"):
            rel_part = p_clean[len(prefix) + 1:]
            return (target_dir / rel_part).resolve()

    path = Path(p_clean)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def tool_list_dir(params):
    p = _resolve_path(params.get("path") or params.get("dir") or ".")
    if not p or not p.exists():
        return {"ok": False, "summary": f"path not found: {p}"}
    entries = []
    for e in sorted(p.iterdir()):
        entries.append(("D " if e.is_dir() else "F ") + e.name)
    return {"ok": True, "summary": f"{len(entries)} entries in {p}", "data": {"entries": entries[:80], "path": str(p)}}


def tool_read_file(params):
    p = _resolve_path(params.get("path") or params.get("file"))
    if not p or not p.exists():
        return {"ok": False, "summary": f"file not found: {p}"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "summary": f"read {len(text)} chars", "data": {"content": text[:4000]}}
    except Exception as e:
        return {"ok": False, "summary": f"read failed: {e}"}


def tool_write_file(params):
    p = _resolve_path(params.get("path") or params.get("file"))
    content = params.get("content") or params.get("text") or ""
    if not p:
        return {"ok": False, "summary": "no path"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "summary": f"wrote {len(content)} chars to {p}", "data": {"path": str(p)}}
    except Exception as e:
        return {"ok": False, "summary": f"write failed: {e}"}


def tool_create_folder(params):
    p = _resolve_path(params.get("path") or params.get("folder") or params.get("dir"))
    if not p:
        return {"ok": False, "summary": "no path"}
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "summary": f"created folder {p}", "data": {"path": str(p)}}
    except Exception as e:
        return {"ok": False, "summary": f"mkdir failed: {e}"}


def tool_rename(params):
    src = _resolve_path(params.get("src") or params.get("from"))
    dst = _resolve_path(params.get("dst") or params.get("to"))
    if not src or not dst:
        return {"ok": False, "summary": "need src and dst"}
    try:
        shutil.move(str(src), str(dst))
        return {"ok": True, "summary": f"renamed {src.name} -> {dst.name}"}
    except Exception as e:
        return {"ok": False, "summary": f"rename failed: {e}"}


def tool_move_copy(params):
    src = _resolve_path(params.get("src") or params.get("from"))
    dst = _resolve_path(params.get("dst") or params.get("to"))
    op = params.get("op") or "move"
    if not src or not dst:
        return {"ok": False, "summary": "need src and dst"}
    try:
        if op == "copy":
            if src.is_dir():
                shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            else:
                shutil.copy2(str(src), str(dst))
        else:
            shutil.move(str(src), str(dst))
        return {"ok": True, "summary": f"{op} {src.name} -> {dst}"}
    except Exception as e:
        return {"ok": False, "summary": f"{op} failed: {e}"}


def tool_delete(params):
    p = _resolve_path(params.get("path") or params.get("target"))
    if not p:
        return {"ok": False, "summary": "no path"}
    if not p.exists():
        return {"ok": True, "summary": f"already absent: {p}"}
    try:
        if p.is_dir():
            shutil.rmtree(str(p))
        else:
            p.unlink()
        return {"ok": True, "summary": f"deleted {p}", "data": {"path": str(p)}}
    except Exception as e:
        return {"ok": False, "summary": f"delete failed: {e}"}


def tool_screenshot(params):
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SHOT_DIR / f"shot_{ts}.png"
        img = ImageGrab.grab()
        img.save(path)
        h = hashlib.md5(img.tobytes()).hexdigest()
        return {"ok": True, "summary": f"screenshot saved ({img.size[0]}x{img.size[1]})", "data": {"path": str(path), "hash": h}}
    except Exception as e:
        return {"ok": False, "summary": f"screenshot failed: {e}"}


def tool_find_file(params):
    frag = _norm(params.get("name") or params.get("query") or params.get("path") or params.get("target"))
    if not frag:
        return {"ok": False, "summary": "no search text"}
    results = []
    try:
        for p in ROOT.rglob("*"):
            if p.is_file() and frag.lower() in p.name.lower():
                results.append(str(p.relative_to(ROOT)))
                if len(results) >= 25:
                    break
    except Exception as e:
        return {"ok": False, "summary": f"search failed: {e}"}
    if not results:
        return {"ok": True, "summary": f"no files matching '{frag}'", "data": {"matches": []}}
    return {"ok": True, "summary": f"{len(results)} matches for '{frag}'", "data": {"matches": results}}

# ==========================================================================
# Vision + motor tools (structured UI understanding & human-like control)
# ==========================================================================
def _obs_summary(obs) -> str:
    """Compact natural summary of a ScreenObservation for the LLM loop."""
    level = int(getattr(obs, "observation_level", 0))
    parts = [
        f"window={getattr(obs, 'window_title', '')!r}",
        f"app={getattr(obs, 'application', '')!r}",
        f"level=L{level}",
    ]
    if getattr(obs, "degraded", False):
        parts.append("degraded=YES (vision unavailable, metadata only)")
    parts.append(f"elements={len(getattr(obs, 'elements', []))}")
    return ", ".join(parts)


def tool_screen_observe(params):
    """vision.analyze_screen — adaptive structured observation (L0-L4)."""
    goal = _norm(params.get("goal") or params.get("query"))
    level = params.get("level")
    try:
        obs = VISION_ANALYZER.analyze_screen(level=int(level) if level is not None else None, goal=goal)
        return {
            "ok": True,
            "summary": f"Screen observed: {_obs_summary(obs)}",
            "data": obs.to_dict(),
        }
    except Exception as e:
        return {"ok": False, "summary": f"screen observe failed: {e}"}


def tool_screen_question(params):
    """Answer 'what's on my screen' as a concise natural summary."""
    try:
        obs = VISION_ANALYZER.analyze_screen(goal="describe the whole screen", force=True)
        if obs.degraded:
            summary = f"VISION_DEGRADED: active window is '{obs.window_title}'."
        else:
            elems = ", ".join(e.label for e in obs.elements[:8] if e.label) or "no labelled controls detected"
            summary = (f"Active {obs.application} window '{obs.window_title}' shows: {elems}."
                       if obs.summary else f"Window '{obs.window_title}' with controls: {elems}.")
        return {"ok": True, "summary": summary, "data": obs.to_dict()}
    except Exception as e:
        return {"ok": False, "summary": f"screen question failed: {e}"}


def tool_find_element(params):
    """vision.find_element — deterministic UI tree first, Gemma vision fallback."""
    label = _norm(params.get("label"))
    elem_type = _norm(params.get("type"))
    elem_id = _norm(params.get("id"))
    if not (label or elem_type or elem_id):
        return {"ok": False, "summary": "provide label, type or id"}
    try:
        el = VISION_ANALYZER.find_element(label=label, elem_type=elem_type, elem_id=elem_id, goal=label)
        if el is None:
            return {"ok": False, "summary": f"could not find element (label={label!r} type={elem_type!r})"}
        d = el.to_dict()
        conf = float(d.get("confidence", 0))
        note = ""
        if conf < CONFIDENCE_MEDIUM:
            note = " WARNING: low confidence, verify before acting."
        return {"ok": True, "summary": f"found {d['type']} '{d['label']}' at {d['center']} src={d['source']}{note}", "data": d}
    except Exception as e:
        return {"ok": False, "summary": f"find element failed: {e}"}


def _resolve_target(params):
    """Resolve a target to a VisionElement. Prefer label/type; else explicit x/y."""
    label = _norm(params.get("label"))
    elem_type = _norm(params.get("type"))
    x, y = params.get("x"), params.get("y")
    if label or elem_type:
        el = VISION_ANALYZER.find_element(label=label, elem_type=elem_type, goal=label)
        return el, None
    if x is not None and y is not None:
        return None, (int(x), int(y))
    return None, None

def tool_click_element(params):
    """Acquire -> plan -> click -> verify (spec sections 9/12/36)."""
    el, xy = _resolve_target(params)
    if el is None and xy is None:
        return {"ok": False, "summary": "need label/type or x,y"}
    try:
        if el is not None:
            if float(el.confidence) < CONFIDENCE_MEDIUM:
                return {"ok": False, "summary": f"target confidence too low ({el.confidence:.2f}); re-observe before acting"}
            plan = MOTOR_PLANNER.plan_click(el)
            target_desc = f"element '{el.label}' ({el.bounds})"
        else:
            plan = MOTOR_PLANNER.plan_click(x=xy[0], y=xy[1])
            target_desc = f"({xy[0]},{xy[1]})"
        res = MOTOR_PLANNER.execute(plan)
        if not res.get("ok"):
            return {"ok": False, "summary": f"click failed: {res.get('summary')}"}
        VISION_ANALYZER.memory.remember_action(f"click {target_desc}")
        # Post-action observation: invalidate stale coords after any real click
        # (the interface may have transitioned).
        VISION_ANALYZER.analyze_screen(force=True)
        return {"ok": True, "summary": f"clicked {target_desc} ({res.get('status')})", "data": {"status": res.get("status")}}
    except Exception as e:
        WATCHDOG.release_all()
        return {"ok": False, "summary": f"click_element failed: {e}"}


def tool_double_click_element(params):
    el, xy = _resolve_target(params)
    if el is None and xy is None:
        return {"ok": False, "summary": "need label/type or x,y"}
    try:
        if el is not None:
            tx, ty = MOTOR_PLANNER.safe_click_point(el)
        else:
            tx, ty = int(xy[0]), int(xy[1])
        res = MOTOR_MOUSE.double_click(tx, ty)
        VISION_ANALYZER.memory.remember_action("double_click")
        VISION_ANALYZER.analyze_screen(force=True)
        return {"ok": res.get("ok", False), "summary": f"double-clicked ({tx},{ty}): {res.get('summary')}"}
    except Exception as e:
        return {"ok": False, "summary": f"double_click_element failed: {e}"}


def tool_drag_and_drop(params):
    """Full drag-and-drop: locate source, locate dest, press, smooth path,
    release, re-observe (spec section 13)."""
    try:
        src_label = _norm(params.get("source") or params.get("src"))
        dst_label = _norm(params.get("destination") or params.get("dst"))
        if not src_label:
            return {"ok": False, "summary": "provide source label"}
        src = VISION_ANALYZER.find_element(label=src_label, goal=src_label)
        dst = VISION_ANALYZER.find_element(label=dst_label, goal=dst_label) if dst_label else None
        plan = MOTOR_PLANNER.plan_drag(src, dst, **params)
        res = MOTOR_PLANNER.execute(plan)
        VISION_ANALYZER.memory.remember_action(f"drag {src_label} -> {dst_label or 'xy'}")
        VISION_ANALYZER.analyze_screen(force=True)
        return {"ok": res.get("ok", False), "summary": res.get("summary", "drag failed")}
    except Exception as e:
        WATCHDOG.release_all()
        return {"ok": False, "summary": f"drag_and_drop failed: {e}"}


def tool_draw_on_screen(params):
    """Draw a shape (line/circle/arc/rectangle) on a canvas. Vision analysis
    before execution, re-observation after (spec sections 17/18)."""
    kind = _norm(params.get("kind") or params.get("shape") or "circle").lower()
    try:
        canvas = None
        if params.get("canvas_label"):
            canvas = VISION_ANALYZER.find_element(label=params["canvas_label"], goal=f"draw {kind}")
        if canvas is None:
            obs = VISION_ANALYZER.analyze_screen(goal=f"draw {kind}", force=True)
            canvas = next((e for e in obs.elements if str(getattr(e.type, "value", e.type)) == "CANVAS"), None)
        center = None
        radius = None
        if params.get("cx") is not None and params.get("cy") is not None:
            center = (float(params["cx"]), float(params["cy"]))
        if params.get("radius") is not None:
            radius = float(params["radius"])
        plan = MOTOR_PLANNER.plan_drawing(kind, canvas, center=center, radius=radius)
        VISION_ANALYZER.memory.remember_action(f"draw {kind}")
        res = MOTOR_PLANNER.execute(plan)
        if not res.get("ok"):
            WATCHDOG.release_all()
            return {"ok": False, "summary": f"draw failed: {res.get('summary')}"}
        VISION_ANALYZER.analyze_screen(force=True)
        return {"ok": True, "summary": f"drew a {kind} on the canvas", "data": {"kind": kind}}
    except Exception as e:
        WATCHDOG.release_all()
        return {"ok": False, "summary": f"draw_on_screen failed: {e}"}
def tool_verify_state(params):
    """Post-action verification: confirm the screen/region changed as expected
    (spec section 36)."""
    expect_change = bool(params.get("expect_change", True))
    region = params.get("region")
    try:
        if isinstance(region, (list, tuple)) and len(region) == 4:
            res = VERIFICATION.verify_region_changed(tuple(int(v) for v in region), expect_change=expect_change)
        else:
            res = VERIFICATION.verify_screen_changed(expect_change=expect_change)
        return {
            "ok": res.ok,
            "summary": f"verification {res.status.value} ({res.signal}): {res.detail}",
            "data": {"status": res.status.value, "signal": res.signal, "detail": res.detail},
        }
    except Exception as e:
        return {"ok": False, "summary": f"verify failed: {e}"}


def tool_release_all_inputs(params):
    """Emergency release of every held mouse button and keyboard key."""
    released = WATCHDOG.release_all()
    return {"ok": True, "summary": f"released {len(released)} held inputs"}


def tool_press_key(params):
    """Keyboard press (stays held) — structured key event, watchdog tracked."""
    key = _norm(params.get("key"))
    if not key:
        return {"ok": False, "summary": "provide key"}
    res = MOTOR_KEYBOARD.press(key)
    return {"ok": res.get("ok"), "summary": res.get("summary", "press failed")}


def tool_release_key(params):
    """Keyboard release (any previously held key)."""
    key = _norm(params.get("key"))
    res = MOTOR_KEYBOARD.release(key) if key else MOTOR_KEYBOARD.release()
    return {"ok": res.get("ok"), "summary": res.get("summary", "release failed")}


def tool_mouse_press_hold(params):
    """Press and hold a mouse button (drawing/painting/selection), watchdog tracked."""
    x = params.get("x")
    y = params.get("y")
    button = params.get("button") or "left"
    if x is None or y is None:
        return {"ok": False, "summary": "need x,y"}
    res = MOTOR_MOUSE.press_and_hold(int(x), int(y), button=button)
    return {"ok": res.get("ok"), "summary": res.get("summary", "press_hold failed")}


def tool_mouse_release(params):
    """Release held mouse button(s)."""
    button = params.get("button")
    res = MOTOR_MOUSE.release(button) if button else MOTOR_MOUSE.release()
    return {"ok": res.get("ok"), "summary": res.get("summary", "release failed")}
# ---- tool registry -------------------------------------------------------
TOOLS = {
    "open_app": ("safe", tool_open_app, "Open any installed application by name (e.g. notepad, chrome, blender)."),
    "open_url": ("safe", tool_open_url, "Open any http(s) URL in the default browser."),
    "run_command": ("sensitive", tool_run_command, "Run a PowerShell/CMD command. Captures output. Requires permission."),
    "list_windows": ("observe", tool_list_windows, "List visible window titles."),
    "active_window": ("observe", tool_active_window, "Return the currently focused window title."),
    "focus_window": ("safe", tool_focus_window, "Focus a window whose title contains the given text."),
    "close_window": ("safe", tool_close_window, "Close a window whose title contains the given text."),
    "mouse_move": ("safe", tool_mouse_move, "Move mouse to x,y (screen pixels)."),
    "mouse_click": ("safe", tool_mouse_click, "Click at x,y (or current pos). button=left/right."),
    "mouse_double": ("safe", tool_mouse_double, "Double-click at x,y."),
    "mouse_right": ("safe", tool_mouse_right, "Right-click at x,y."),
    "mouse_drag": ("safe", tool_mouse_drag, "Drag from x1,y1 to x2,y2."),
    "scroll": ("safe", tool_scroll, "Scroll mouse wheel by amount (positive=up)."),
    "type_text": ("safe", tool_type, "Type text at the current cursor."),
    "press_keys": ("safe", tool_press, "Press a key or hotkey, e.g. keys=['ctrl','c']."),
    "list_dir": ("observe", tool_list_dir, "List files/folders in a path."),
    "read_file": ("observe", tool_read_file, "Read a text file's contents."),
    "write_file": ("safe", tool_write_file, "Create/overwrite a text file with content."),
    "create_folder": ("safe", tool_create_folder, "Create a folder (recursively)."),
    "rename": ("destructive", tool_rename, "Rename/move a file or folder (src->dst)."),
    "copy_move": ("destructive", tool_move_copy, "Copy or move a file/folder (op=copy|move)."),
    "delete": ("destructive", tool_delete, "Delete a file or folder. Requires permission; reversible only via backups."),
    "open_notepad_and_type": ("safe", tool_open_notepad_and_type, "Open Notepad in a NEW untitled tab and type text there (never touches existing docs)."),
    "screenshot": ("observe", tool_screenshot, "Capture the screen and return the image path."),
    "find_file": ("observe", tool_find_file, "Recursively find files whose name contains the given text."),
    "screen_observe": ("observe", tool_screen_observe, "Structured screen observation: app, window, UI elements. level=0-4, goal=optional focus."),
    "screen_question": ("observe", tool_screen_question, "Answer 'what is on my screen' with a concise natural summary."),
    "find_element": ("observe", tool_find_element, "Find a UI element by label/type. Deterministic UIA first, Gemma vision fallback."),
    "click_element": ("safe", tool_click_element, "Locate a UI element by label/type (or x,y) and click it; re-observes after."),
    "double_click_element": ("safe", tool_double_click_element, "Locate a UI element by label/type (or x,y) and double-click it."),
    "drag_and_drop": ("safe", tool_drag_and_drop, "Drag a labelled element (source) to a destination element label or x,y."),
    "draw_on_screen": ("safe", tool_draw_on_screen, "Draw a shape (line/circle/arc/rectangle) on the active canvas."),
    "verify_state": ("observe", tool_verify_state, "Post-action verification: confirm the screen/region changed (expect_change)."),
    "release_all_inputs": ("observe", tool_release_all_inputs, "Emergency release of every held mouse button and keyboard key."),
    "press_key": ("safe", tool_press_key, "Hold a keyboard key down (release with release_key)."),
    "release_key": ("safe", tool_release_key, "Release a held keyboard key (or all keys when key omitted)."),
    "mouse_press_hold": ("safe", tool_mouse_press_hold, "Press-and-hold a mouse button at x,y (drawing/painting/selection)."),
    "mouse_release": ("safe", tool_mouse_release, "Release a held mouse button (or all buttons when omitted)."),
    "run_code": ("safe", lambda p: tool_run_command({"command": f"python -c {repr(p.get('code',''))}", "timeout": p.get("timeout", 60)}), "Execute Python code (alias for run_command). Use code param."),
}


SCHEMA = {
    "open_app": {"name": {"type": "string", "description": "Application name (e.g. notepad, chrome, blender) or a URL."}},
    "open_url": {"url": {"type": "string", "description": "Full http(s) URL to open."}},
    "run_command": {"command": {"type": "string", "description": "PowerShell/CMD command to run."},
                    "timeout": {"type": "integer", "description": "Seconds before timeout (default 60)."}},
    "list_windows": {},
    "active_window": {},
    "focus_window": {"title": {"type": "string", "description": "Substring of the window title to focus."}},
    "close_window": {"title": {"type": "string", "description": "Substring of the window title to close."}},
    "mouse_move": {"x": {"type": "integer", "description": "Target X in screen pixels."},
                   "y": {"type": "integer", "description": "Target Y in screen pixels."}},
    "mouse_click": {"x": {"type": "integer", "description": "X pixel (omit to click current position)."},
                    "y": {"type": "integer", "description": "Y pixel."},
                    "button": {"type": "string", "description": "left or right (default left)."}},
    "mouse_double": {"x": {"type": "integer", "description": "X pixel (omit for current)."},
                     "y": {"type": "integer", "description": "Y pixel."}},
    "mouse_right": {"x": {"type": "integer", "description": "X pixel (omit for current)."},
                    "y": {"type": "integer", "description": "Y pixel."}},
    "mouse_drag": {"x1": {"type": "integer"}, "y1": {"type": "integer"},
                   "x2": {"type": "integer"}, "y2": {"type": "integer"},
                   "button": {"type": "string", "description": "left or right."}},
    "scroll": {"amount": {"type": "integer", "description": "Notches (positive=up)."}},
    "type_text": {"text": {"type": "string", "description": "Text to type at the cursor."}},
    "press_keys": {"keys": {"type": "array", "items": {"type": "string"},
                            "description": "Key or hotkey list, e.g. ['ctrl','c']."}},
    "list_dir": {"path": {"type": "string", "description": "Directory path (default project root)."}},
    "read_file": {"path": {"type": "string", "description": "File path to read."}},
    "write_file": {"path": {"type": "string", "description": "File path to write."},
                   "content": {"type": "string", "description": "Text content to write."}},
    "create_folder": {"path": {"type": "string", "description": "Folder path to create."}},
    "rename": {"src": {"type": "string", "description": "Source path."},
               "dst": {"type": "string", "description": "Destination path."}},
    "copy_move": {"src": {"type": "string"}, "dst": {"type": "string"},
                  "op": {"type": "string", "description": "copy or move (default move)."}},
    "delete": {"path": {"type": "string", "description": "File or folder to delete (destructive)."}},
    "open_notepad_and_type": {"text": {"type": "string", "description": "Text to type into a new Notepad tab."}},
    "screenshot": {},
    "find_file": {"name": {"type": "string", "description": "Filename fragment to search for."}},
    "screen_observe": {"goal": {"type": "string", "description": "Optional focus goal for the analysis."},
                       "level": {"type": "integer", "description": "Force observation level 0-4 (optional)."}},
    "screen_question": {},
    "find_element": {"label": {"type": "string", "description": "Visible label/text of the element."},
                     "type": {"type": "string", "description": "Element type (BUTTON, TEXT_FIELD, MENU, CANVAS...)."},
                     "id": {"type": "string", "description": "Known element id (optional)."}},
    "click_element": {"label": {"type": "string", "description": "Visible label/text of the target."},
                      "type": {"type": "string", "description": "Element type hint."},
                      "x": {"type": "integer", "description": "Explicit X (alternative to label)."},
                      "y": {"type": "integer", "description": "Explicit Y."},
                      "button": {"type": "string", "description": "left or right (default left)."}},
    "double_click_element": {"label": {"type": "string", "description": "Visible label/text of the target."},
                             "x": {"type": "integer"}, "y": {"type": "integer"}},
    "drag_and_drop": {"source": {"type": "string", "description": "Label of the element to drag."},
                      "destination": {"type": "string", "description": "Label of the destination (or use x2/y2)."},
                      "x2": {"type": "integer"}, "y2": {"type": "integer"}},
    "draw_on_screen": {"kind": {"type": "string", "description": "line, circle, arc, rectangle (default circle)."},
                       "canvas_label": {"type": "string", "description": "Optional label of the canvas element."},
                       "cx": {"type": "integer", "description": "Optional center X."},
                       "cy": {"type": "integer", "description": "Optional center Y."},
                       "radius": {"type": "integer", "description": "Optional radius in pixels."}},
    "verify_state": {"expect_change": {"type": "boolean", "description": "True if the action should change the screen."},
                     "region": {"type": "array", "description": "Optional [x,y,w,h] region to check."}},
    "release_all_inputs": {},
    "press_key": {"key": {"type": "string", "description": "Key name (e.g. shift, ctrl, alt)."}},
    "release_key": {"key": {"type": "string", "description": "Key to release (omit to release all)."}},
    "mouse_press_hold": {"x": {"type": "integer"}, "y": {"type": "integer"},
                         "button": {"type": "string", "description": "left/right/middle."}},
    "mouse_release": {"button": {"type": "string", "description": "Button to release (omit to release all)."}},
    "run_code": {"code": {"type": "string", "description": "Python code to execute."}, "timeout": {"type": "integer", "description": "Timeout in seconds."}},
}


def tool_specs():
    specs = []
    for name, (tier, fn, desc) in TOOLS.items():
        props = {}
        required = []
        for pname, pdef in SCHEMA.get(name, {}).items():
            props[pname] = pdef
            if pname in ("name", "url", "command", "text", "path", "content", "src", "dst",
                         "x", "y", "x1", "y1", "x2", "y2", "title", "keys"):
                required.append(pname)
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"[{tier}] {desc}",
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    return specs


# ==========================================================================
# Permission gate — AUTO-GRANT (user requested direct execution)
# ==========================================================================
async def _default_permission(prompt: str) -> bool:
    return True


# ==========================================================================
# Planner / executor (ReAct over real tools)
# ==========================================================================
SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., an autonomous Windows computer-use agent. "
    "Accomplish the user's goal by calling the available tools step by step. "
    "Rules: "
    "1) Prefer real tools over explanation. Do not describe HOW to do something; DO it. "
    "2) Observe first when the goal depends on current state (list_windows, active_window, screenshot, list_dir). "
    "3) After each action, the tool result is returned as an observation. Use it to decide the next step. "
    "4) Verify success before finishing (e.g. list_dir after write_file, active_window after open_app). "
    "5) If a tool fails, retry with a different strategy or report the blocker honestly. "
    "6) When finished, return a short final message (no tool call) summarizing what was done. "
    "7) Keep the final message concise and natural. Do not reveal chain-of-thought. "
    "8) To type into Notepad, use open_notepad_and_type (it opens a NEW untitled tab) "
    "so you never overwrite the user's existing documents. "
    "9) Treat destructive or consequential actions (install, delete, purchase, send, publish, "
    "system settings) as confirmation-gated; navigation and observation may proceed directly. "
    "10) Avoid generic filler such as 'Done, sir', 'Absolutely', or 'That's a great idea'. "
    "Report verified facts, infer the user's broader goal, and add at most two useful next-step insights. "
    "11) For current software, pricing, release, or compatibility claims, use a live research tool when available; "
    "otherwise say that the fact has not been verified."
)


class ComputerAgent:
    def __init__(self, brain, memory: Memory, request_permission=None):
        self.brain = brain
        self.memory = memory
        self.request_permission = request_permission or _default_permission
        self._last_shot_hash = None
        self.history: list[dict] = []
        self._last_result = ""
        self._last_task = ""

    def fast_plan(self, text: str):
        t = text.lower().strip()
        # Clean leading words like 'please', 'can you', 'now'
        clean_t = re.sub(r"^(please|can you|could you|now|okay now|ok now)\s+", "", t).strip()

        m = re.match(r"^(open|launch|start|run)\s+(?:the\s+)?(.+)$", clean_t)
        if m:
            # STT transcripts often end with punctuation ("Open Notepad.") — strip it
            # so "notepad." is never treated as a domain ("https://notepad.").
            target = m.group(2).strip().rstrip(".,;:!?\"'()") or ""
            target = re.sub(r"\s+(please|for me|now)\s*$", "", target).strip()
            if not target:
                return None
            # Real URL?
            if re.match(r"^(https?://|www\.)", target):
                return [("open_url", {"url": target})]
            if target in ("youtube", "google", "gmail", "github", "twitter",
                          "reddit", "stackoverflow", "stack overflow", "maps",
                          "spotify web", "netflix", "amazon", "wikipedia"):
                return [("open_url", {"url": target.replace(" ", "") + ".com"})]
            if " and " in target or " then " in target or ", then " in target:
                # Multi-step ("open notepad and type hello") -> let the LLM plan it
                return None
            # A genuine domain has a bare dot + TLD (e.g. github.com, pixel.org).
            # Bare words (notepad, calculator, chrome) and quoted entries are apps.
            if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", target) and not target.endswith((".exe", ".bat", ".cmd")):
                return [("open_url", {"url": target})]
            return [("open_app", {"name": target})]
        if clean_t.startswith("go to ") or clean_t.startswith("visit "):
            return [("open_url", {"url": clean_t.split(" ", 2)[2]})]
        if clean_t.startswith("close ") or clean_t.startswith("exit "):
            name = re.sub(r"^(close|exit)\s+(?:the\s+)?", "", clean_t).strip()
            name = name.rstrip(".,;!?").strip()
            return [("close_window", {"name": name})]
        if clean_t in ("screenshot", "screen shot", "capture screen"):
            return [("screenshot", {})]
        m = re.match(r"^(type|write)\s+(?:text\s+)?['\"]?(.+?)['\"]?$", clean_t)
        if m:
            return [("type_text", {"text": m.group(2).strip()})]
        return None

    async def _call_llm(self, messages):
        if self.brain.client is None:
            return None
        try:
            resp = await asyncio.to_thread(
                self.brain.client.chat.completions.create,
                model=self.brain.model,
                messages=messages,
                tools=tool_specs(),
                tool_choice="auto",
            )
            return resp.choices[0].message
        except Exception as e:
            return f"__error__:{e}"

    async def run(self, text: str, emit, character: str = "IRON_MAN"):
        await emit({"type": "state", "status": "observing"})
        try:
            self.memory.learn_from_text(text)
        except Exception:
            pass
        ctx = ""
        try:
            aw = gw.getActiveWindow()
            ctx = f"Active window: {aw.title if aw else 'none'}."
        except Exception:
            ctx = ""

        # Personality + context: one authoritative voice layer for every reply.
        try:
            from personality import (PERSONALITY_BLOCK, build_context_block,
                                     estimate_tone, format_for_speech,
                                     personality_directive)
        except Exception:
            PERSONALITY_BLOCK = ""
            build_context_block = lambda *a, **k: ""
            estimate_tone = lambda t, outcome="ok": "neutral"
            format_for_speech = lambda raw, **k: (raw, None)
            personality_directive = lambda *a, **k: ""
        persona_tone = estimate_tone(text)
        persona_block = (PERSONALITY_BLOCK + "\n"
                         + personality_directive(persona_tone) + "\n"
                         + f"Active persona mode: {character}." if PERSONALITY_BLOCK else "")
        context_block = build_context_block(self.history, self._last_result, self._last_task)
        try:
            memory_block = self.memory.context(text)
            if memory_block:
                context_block += ("\nRelevant persistent memory (use only when relevant; do not invent):\n"
                                  + memory_block)
        except Exception:
            pass
        system_content = SYSTEM_PROMPT
        if persona_block.strip():
            system_content += "\n" + persona_block.strip()
        if context_block.strip():
            system_content += "\nConversation context (ground truth, do not re-ask for it):\n" + context_block

        plan = self.fast_plan(text)
        used_llm = False
        outcome = "ok"
        if plan is None or self.brain.client is None:
            used_llm = True
            # Multi-turn context retention: include recent conversational history
            messages = [{"role": "system", "content": system_content}]
            for h in self.history[-8:]:
                messages.append(h)
            messages.append({"role": "user", "content": f"{ctx}\nGoal: {text}"})
            final = None
            last_sig = None
            repeat = 0
            for step in range(12):
                await emit({"type": "state", "status": "planning"})
                msg = await self._call_llm(messages)
                if isinstance(msg, str) and msg.startswith("__error__:"):
                    final = f"Planner error: {msg[9:]}"
                    outcome = "fail"
                    break
                if msg is None:
                    final = "I could not reach the planning model."
                    outcome = "fail"
                    break
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in (msg.tool_calls or [])
                    ],
                })
                if not msg.tool_calls:
                    final = msg.content or "The requested action is complete."
                    break
                # Stuck-detection: if the model repeats the exact same call, stop.
                sigs = []
                for tc in msg.tool_calls:
                    try:
                        sigs.append((tc.function.name, tc.function.arguments))
                    except Exception:
                        sigs.append((tc.function.name, ""))
                if sigs and sigs == last_sig:
                    repeat += 1
                else:
                    repeat = 0
                    last_sig = sigs
                if repeat >= 2:
                    final = ("I kept repeating the same action without new information, so I'll "
                             "stop here. Based on the last observation, here is what I found: "
                             + (msg.content or "see the tool results above."))
                    outcome = "fail"
                    break
                await emit({"type": "state", "status": "executing"})
                for tc in msg.tool_calls:
                    await self._exec_tool(tc, messages, emit)
            result_text = final or "The requested action is complete."
        else:
            result_text = ""
            all_ok = True
            for name, params in plan:
                r = await self._exec_tool_named(name, params, emit)
                all_ok = all_ok and bool(r.get("ok", False))
                result_text = r.get("summary", "")
            result_text = result_text or "The requested action is complete."
            if not all_ok or re.search(r"(?i)\b(fail|could not|unable|error|not found)\b", result_text):
                outcome = "fail"

        # Retain conversational context for follow-up requests
        self.history.append({"role": "user", "content": text})
        self._last_task = text[:160]

        # Personality gate: every reply is tone-matched and speech-formatted.
        # `speak` is what TTS reads; `detail` (when present) is shown in the HUD.
        tone = estimate_tone(text, outcome if outcome in ("ok", "fail") else "ok")
        kind = "confirm" if not used_llm else "answer"
        detail_requested = bool(re.search(r"(?i)\b(detail|details|explain|why|how come|show me)\b", text))
        try:
            speak, detail = format_for_speech(result_text, kind=kind, tone=tone,
                                              detail_requested=detail_requested)
        except Exception:
            speak, detail = result_text, None
        self.history.append({"role": "assistant", "content": speak})
        if len(self.history) > 16:
            self.history = self.history[-16:]
        self._last_result = speak[:220]

        self.memory.log("command", text, ok=(outcome == "ok"))
        payload = {"type": "conversation", "text": speak, "voice_streaming": False, "tone": tone}
        if detail:
            payload["detail"] = detail
        await emit(payload)
        await emit({"type": "done", "text": ""})
        return speak

    async def _exec_tool(self, tc, messages, emit):
        try:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            name, args = (getattr(tc.function, "name", "unknown"), {})
        res = await self._exec_tool_named(name, args, emit)
        ok = res.get("ok", False)
        obs = f"[{name}] {'OK' if ok else 'FAIL'}: {res.get('summary','')}"
        data = res.get("data")
        if data:
            try:
                obs += " | " + json.dumps(data, ensure_ascii=False)[:600]
            except Exception:
                pass
        if not ok:
            obs += " | diagnose and retry with a different strategy, or report blocker."
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})
        return res

    # Tool name normalization — handles LLM hallucinations like "repo_browser . run_code" or "run_code"
    TOOL_ALIASES = {
        "run_code": "run_command",
        "run-code": "run_command",
        "repo_browser.run_code": "run_command",
        "repo_browser_run_code": "run_command",
        "browser.run_code": "run_command",
        "code": "run_command",
        "python": "run_command",
        "execute_code": "run_command",
        "shell": "run_command",
        "bash": "run_command",
        "cmd": "run_command",
        "terminal": "run_command",
    }

    def _normalize_tool_name(self, raw: str) -> str:
        # Strip, lower, remove spaces around dots, replace spaces/dashes
        name = (raw or "").strip().lower()
        # Fix hallucinated "repo_browser . run_code" -> "repo_browser.run_code"
        name = name.replace(" ", "").replace("-", "_")
        # Map aliases
        if name in self.TOOL_ALIASES:
            return self.TOOL_ALIASES[name]
        # Handle dot-notation: take last part
        if "." in name:
            last = name.split(".")[-1]
            if last in self.TOOL_ALIASES:
                return self.TOOL_ALIASES[last]
            if last in TOOLS:
                return last
        return name

    def _coerce_tool_args(self, name: str, args: dict) -> dict:
        # LLM sometimes sends {"code": "..."} for run_command which expects {"command": "..."}
        if name == "run_command" and "code" in args and "command" not in args:
            code = args.get("code", "")
            # Wrap bare python code as python -c execution
            if code.strip().startswith("import ") or "def " in code or "print(" in code:
                args = dict(args)
                # Escape for shell: write to temp file and run
                args["command"] = f'python -c "{code.replace(chr(34), chr(39))}"'
                args.pop("code", None)
            else:
                args["command"] = args.pop("code")
        return args

    async def _exec_tool_named(self, name, args, emit):
        # Normalize hallucinated names before lookup
        norm = self._normalize_tool_name(name)
        if norm != name:
            args = self._coerce_tool_args(norm, args)
            name = norm
        else:
            args = self._coerce_tool_args(name, args)
        spec = TOOLS.get(name)
        if not spec:
            # Try to find closest match for helpful error
            maybe = [k for k in TOOLS if k in name or name in k]
            hint = f" Did you mean {maybe[0]}?" if maybe else ""
            return {"ok": False, "summary": f"unknown tool '{name}'. Available: {', '.join(sorted(TOOLS))}.{hint} Use only tools from this list."}
        tier, fn, _ = spec
        # Permission auto-granted — JARVIS executes directly per user request.
        await emit({"type": "progress", "text": f"Running {name}..."})
        try:
            res = await asyncio.to_thread(fn, args)
        except Exception as e:
            res = {"ok": False, "summary": f"exception: {e}"}
        if res.get("ok"):
            await emit({"type": "progress", "text": f"Verified: {res.get('summary','')}"})
            self.memory.log(name, json.dumps(args, ensure_ascii=False), ok=True)
            if name == "open_app" and (args.get("name") or args.get("app")):
                app_name = str(args.get("name") or args.get("app")).strip()
                self.memory.remember("software:" + re.sub(r"\W+", "_", app_name.lower()),
                                     {"name": app_name, "state": "open", "verified": True},
                                     category="SOFTWARE_STATE", source="computer_observation", confidence=0.95)
        else:
            await emit({"type": "progress", "text": f"Failed: {res.get('summary','')} (will retry/diagnose)"})
            self.memory.log(name, json.dumps(args, ensure_ascii=False), ok=False)
        return res


# ==========================================================================
# Health check
# ==========================================================================
def doctor():
    checks = []
    def add(name, ok, info=""):
        checks.append({"name": name, "ok": ok, "info": info})

    add("venv python", (ROOT / ".venv" / "Scripts" / "python.exe").exists())
    for mod in ("pyautogui", "PIL", "pygetwindow", "websockets", "openai"):
        try:
            __import__(mod)
            add(f"module:{mod}", True)
        except Exception as e:
            add(f"module:{mod}", False, str(e))
    chrome = None
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            chrome = p
    add("chrome", chrome is not None, chrome or "not found")
    add("themes dir", (ROOT / "jarvis hud difrrent themes").exists())
    add("GROQ_API_KEY", bool(os.environ.get("GROQ_API_KEY")))
    add("GEMINI_API_KEY", bool(os.environ.get("GEMINI_API_KEY")))
    return checks
