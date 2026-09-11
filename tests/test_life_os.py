"""Personal life OS test suite: schedule, reminders, focus, distraction,
overrides, daily state, events, profile, hydration, sleep mode, restart
recovery and the accelerated real-world acceptance timeline.

All engines are pure (clock-injected) — no model calls, no network, no sleep.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jarvis.life import (
    DailyStateManager,
    DistractionMonitor,
    FocusManager,
    LifeAssistant,
    PersonalProfile,
    ReminderEngine,
    RoutineManager,
    ScheduleEngine,
    SpecialEventManager,
    WindowObservation,
)
from jarvis.life.model import FocusState, RoutineBlock, block_covers


def _dt(h: int, m: int = 0, day: int = 19) -> datetime:
    return datetime(2026, 8, day, h, m, 0).astimezone()


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp())


def _life(tmp: Path | None = None, **cfg: object) -> LifeAssistant:
    base = {"hydration": {"enabled": True, "interval_minutes": 30, "quiet_during_sleep": True,
                          "quiet_during_pooja": True, "quiet_during_meals": True,
                          "quiet_minutes_after_ack": 60},
            "reminders": {"enabled": True, "pre_start_minutes": 5, "end_wrapup_minutes": 5},
            "distraction": {"enabled": True, "gentle_delay_seconds": 90, "repeat_minutes": 20,
                            "auto_return_enabled": False},
            "tick_interval_seconds": 30, **cfg}
    life = LifeAssistant(tmp or _tmpdir(), base)
    return life


class DefaultRoutineTests(unittest.TestCase):
    def test_default_routine_loads_structured_schedule(self) -> None:
        tmp = _tmpdir()
        manager = RoutineManager(tmp)
        blocks = manager.blocks()
        self.assertEqual(24, len(blocks))
        self.assertIsInstance(blocks[0], RoutineBlock)
        ids = [b.id for b in blocks]
        self.assertIn("chemistry_deep_study", ids)
        self.assertIn("sleep", ids)
        chemistry = manager.block_by_id("chemistry_deep_study")
        self.assertEqual("07:00", chemistry.start)
        self.assertEqual("09:30", chemistry.end)
        self.assertEqual("chemistry", chemistry.subject)
        self.assertTrue(chemistry.monitor_distractions)
        self.assertFalse(chemistry.entertainment_allowed)

    def test_wake_timezone_boundary(self) -> None:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        # 02:00 belongs to the previous day's cycle (before 04:45 wake).
        early = _dt(2, 0)
        self.assertEqual("sleep", schedule.block_at(early).category)
        self.assertEqual("sleep", schedule.block_at(early).id)

    def test_block_covers_wrap_and_remaining(self) -> None:
        sleep = RoutineBlock(id="sleep", title="Sleep", start="22:00", end="04:45", category="sleep")
        self.assertTrue(block_covers(sleep, 23 * 60 + 30))
        self.assertTrue(block_covers(sleep, 3 * 60))
        self.assertFalse(block_covers(sleep, 5 * 60))
        self.assertFalse(block_covers(sleep, 21 * 60 + 59))

    def test_next_block_after(self) -> None:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        self.assertEqual("breakfast", schedule.next_block_after(_dt(8, 0)).id)
        self.assertEqual("mathematics_deep_study", schedule.next_block_after(_dt(10, 0)).id)
        # Late night wraps to tomorrow's wake.
        self.assertEqual("wake", schedule.next_block_after(_dt(23, 30)).id)


class ReminderEngineTests(unittest.TestCase):
    def _engine(self, tmp: Path) -> tuple[ReminderEngine, DailyStateManager]:
        life = _life(tmp)
        return life.reminders, life.daily

    def test_pre_start_start_end_sequence(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        now = _dt(6, 55)  # 5 min before chemistry
        due = engine.due(now, daily.day(now.date()))
        kinds = {r.kind for r in due}
        self.assertIn("pre", kinds)
        pre = next(r for r in due if r.kind == "pre")
        self.assertIn("chemistry", pre.text)

        now = _dt(7, 0)
        due = engine.due(now, daily.day(now.date()))
        starts = [r for r in due if r.kind == "start"]
        self.assertTrue(starts)
        self.assertIn("Chemistry", starts[0].text)

        now = _dt(9, 25)
        due = engine.due(now, daily.day(now.date()))
        wraps = [r for r in due if r.kind == "wrap"]
        self.assertTrue(wraps)
        self.assertIn("Five minutes left", wraps[0].text)

        now = _dt(9, 29)
        due = engine.due(now, daily.day(now.date()))
        ends = [r for r in due if r.kind == "end"]
        self.assertTrue(ends)
        self.assertIn("complete", ends[0].text)
        self.assertIn("Breakfast", ends[0].text)

        now = _dt(9, 30)
        due = engine.due(now, daily.day(now.date()))
        starts = [r for r in due if r.kind == "start"]
        self.assertTrue(starts)
        self.assertIn("Breakfast", starts[0].text)

    def test_reminders_never_duplicate(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        now = _dt(7, 0)
        day = now.date()
        first = engine.due(now, daily.day(day))
        for r in first:
            daily.mark_fired(day, r.key)
        second = engine.due(now, daily.day(day))
        self.assertEqual(0, len(second))

    def test_hydration_cadence_and_quiet_periods(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        day = _dt(8, 0).date()
        due = engine.due(_dt(8, 0), daily.day(day))
        self.assertTrue(any(r.kind == "hydrate" for r in due))
        # No hydration during meals, pooja or sleep.
        for hm, kind in [("12:35", "meal"), ("05:45", "pooja"), ("23:00", "sleep")]:
            h, m = (int(x) for x in hm.split(":"))
            due = engine.due(_dt(h, m), daily.day(day))
            self.assertFalse(any(r.kind == "hydrate" for r in due), f"hydration during {kind} at {hm}")

    def test_hydration_interval_configurable(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        engine.hydration_cfg["interval_minutes"] = 120
        day = _dt(8, 0).date()
        due = engine.due(_dt(8, 0), daily.day(day))
        self.assertTrue(any(r.kind == "hydrate" for r in due))

    def test_hydration_silent_after_ack(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        day = _dt(8, 0).date()
        daily.record_hydration_ack(day, _dt(8, 0))
        due = engine.due(_dt(8, 5), daily.day(day))
        self.assertFalse(any(r.kind == "hydrate" for r in due))

    def test_morning_greeting_and_sleep(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        day = _dt(4, 45).date()
        due = engine.due(_dt(4, 45), daily.day(day))
        self.assertTrue(any(r.kind == "morning" for r in due))
        due = engine.due(_dt(22, 0), daily.day(day))
        self.assertTrue(any(r.kind == "start" and "sleep" in r.text.lower() for r in due))

    def test_disable_reminders_override(self) -> None:
        tmp = _tmpdir()
        engine, daily = self._engine(tmp)
        day = _dt(6, 55).date()
        daily.add_override(day, {"kind": "disable_reminders"})
        due = engine.due(_dt(6, 55), daily.day(day))
        self.assertEqual([], due)


class FocusManagerTests(unittest.TestCase):
    def test_study_state_machine(self) -> None:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        focus = FocusManager(schedule)
        self.assertEqual("STUDY_STARTING", focus.focus_state(_dt(7, 2)).mode)
        self.assertEqual("STUDY_ACTIVE", focus.focus_state(_dt(8, 0)).mode)
        self.assertEqual("STUDY_ENDING", focus.focus_state(_dt(9, 27)).mode)
        self.assertEqual("chemistry", focus.focus_state(_dt(8, 0)).subject)
        self.assertEqual("BREAK_ACTIVE", focus.focus_state(_dt(10, 15)).mode)
        # 09:31 is right after chemistry — STUDY_COMPLETE in the breakfast block.
        self.assertEqual("STUDY_COMPLETE", focus.focus_state(_dt(9, 31)).mode)
        self.assertEqual("SLEEP", focus.focus_state(_dt(23, 0)).mode)

    def test_remaining_time(self) -> None:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        focus = FocusManager(schedule)
        state = focus.focus_state(_dt(8, 0))
        self.assertEqual(5400, state.remaining_seconds)  # 1.5h left in chemistry


class DistractionMonitorTests(unittest.TestCase):
    def _monitor(self) -> DistractionMonitor:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        return DistractionMonitor(schedule, {"enabled": True, "gentle_delay_seconds": 90,
                                             "repeat_minutes": 20, "auto_return_enabled": False})

    def test_calculator_and_notes_allowed(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(app="Calculator"))
        self.assertEqual("SUPPORTED", r.kind)
        r = monitor.evaluate(_dt(8, 0), WindowObservation(app="notepad", title="notes - Notepad"))
        self.assertEqual("SUPPORTED", r.kind)

    def test_educational_site_supported(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(
            app="chrome", title="Khan Academy", url="https://www.khanacademy.org/science/chemistry"))
        self.assertEqual("SUPPORTED", r.kind)

    def test_social_media_is_distraction_during_study(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(
            app="msedge", title="Instagram", url="https://www.instagram.com/"))
        self.assertEqual("OUT_OF_SCHEDULE", r.kind)

    def test_educational_youtube_exception(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(
            app="chrome", title="Organic Chemistry Reaction Mechanisms - YouTube",
            url="https://www.youtube.com/watch?v=abc123"))
        self.assertEqual("SUPPORTED", r.kind)

    def test_entertainment_youtube_detected(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(
            app="chrome", title="Funny Cartoon Compilation - YouTube",
            url="https://www.youtube.com/watch?v=xyz789"))
        self.assertEqual("OUT_OF_SCHEDULE", r.kind)

    def test_no_monitoring_during_breaks(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(10, 15), WindowObservation(
            app="chrome", title="Funny Cartoon Compilation - YouTube",
            url="https://www.youtube.com/watch?v=xyz789"))
        self.assertEqual("NOT_MONITORED", r.kind)

    def test_unknown_window_not_nagged(self) -> None:
        monitor = self._monitor()
        r = monitor.evaluate(_dt(8, 0), WindowObservation(app="somegame.exe", title="Unknown Game"))
        self.assertEqual("UNKNOWN", r.kind)

    def test_escalation_ladder(self) -> None:
        monitor = self._monitor()
        window = WindowObservation(app="chrome", title="Funny Cartoon Compilation - YouTube",
                                   url="https://www.youtube.com/watch?v=xyz789")
        now = _dt(8, 0)
        base = monitor.evaluate(now, window)
        c1 = monitor.escalate(now, base, window)
        self.assertEqual(1, c1.level)  # wait briefly — no message yet
        c2 = monitor.escalate(now + timedelta(seconds=95), base, window)
        self.assertEqual(2, c2.level)  # gentle reminder
        c3 = monitor.escalate(now + timedelta(seconds=95 + 20 * 60), base, window)
        self.assertEqual(3, c3.level)  # repeat + offer

    def test_auto_return_only_when_enabled(self) -> None:
        schedule = ScheduleEngine(RoutineManager(_tmpdir()).routine)
        monitor = DistractionMonitor(schedule, {"enabled": True, "gentle_delay_seconds": 0,
                                                "repeat_minutes": 1, "auto_return_enabled": True})
        window = WindowObservation(app="chrome", title="Funny Cartoon Compilation - YouTube",
                                   url="https://www.youtube.com/watch?v=xyz789")
        now = _dt(8, 0)
        base = monitor.evaluate(now, window)
        l1 = monitor.escalate(now, base, window).level                                  # first sighting -> L1
        l2 = monitor.escalate(now + timedelta(minutes=2), base, window).level           # L2 gentle reminder
        l3 = monitor.escalate(now + timedelta(minutes=3), base, window).level           # L3 repeat + offer
        l4 = monitor.escalate(now + timedelta(minutes=4), base, window).level           # L4 auto-return
        self.assertEqual([1, 2, 3, 4], [l1, l2, l3, l4])


class OverrideAndCommandTests(unittest.TestCase):
    def test_skip_subject(self) -> None:
        life = _life()
        reply, _ = life.handle_command("routine_override", "skip physics today")
        self.assertIn("skipped", reply)
        state = life.state()
        self.assertIn("skip_block", state["overrides"])

    def test_ignore_day_silences_reminders_and_monitoring(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(6, 55)
        life.handle_command("routine_override", "ignore the routine for today")
        events = life.tick(_dt(6, 55))
        self.assertEqual([], [e for e in events if e.get("kind") == "reminder"])

    def test_extra_break_grants_entertainment(self) -> None:
        life = _life()
        reply, _ = life.handle_command("routine_override", "give me an extra break")
        self.assertIn("Extra break", reply)
        state = life.state(_dt(8, 0))
        self.assertIn("extra_break", state["overrides"])

    def test_move_subject(self) -> None:
        life = _life()
        reply, _ = life.handle_command("routine_override", "move chemistry to 2 pm")
        self.assertIn("moved", reply)
        self.assertIn("shift", life.state()["overrides"])

    def test_exam_mode_toggle(self) -> None:
        life = _life()
        reply, _ = life.handle_command("routine_override", "enable exam mode")
        self.assertIn("EXAM MODE", reply)
        self.assertTrue(life.exam_mode())
        reply, _ = life.handle_command("routine_override", "disable exam mode")
        self.assertFalse(life.exam_mode())

    def test_hydration_ack_and_interval(self) -> None:
        life = _life()
        reply, _ = life.handle_command("hydration_ack", "i drank water")
        self.assertIn("Water logged", reply)
        self.assertEqual(1, life.state()["hydration"]["count"])
        reply, _ = life.handle_command("hydration_ack", "set water reminder interval to 45",
                                       {"interval": 45})
        self.assertIn("45", reply)
        self.assertEqual(45, life.config["hydration"]["interval_minutes"])

    def test_routine_status_reports_current_block(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(8, 0)
        reply, _ = life.handle_command("routine_status", "what am i doing")
        self.assertIn("Chemistry", reply)
        self.assertIn("remaining", reply)

    def test_show_routine_lists_blocks(self) -> None:
        life = _life()
        reply, _ = life.handle_command("show_routine", "show my schedule")
        self.assertIn("Chemistry Deep Study", reply)
        self.assertIn("07:00", reply)


class DistractionExplanationTests(unittest.TestCase):
    def test_study_explanation_accepted_no_interference(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(8, 0)
        reply = life.acknowledge_distraction("I'm watching a chemistry lecture")
        self.assertIn("Understood", reply)
        state = life.state()
        self.assertEqual(1, state["exceptions_today"])

    def test_break_explanation_gets_next_break(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(14, 10)  # during physics study
        reply = life.acknowledge_distraction("I'm taking a quick break")
        self.assertIn("next scheduled break", reply)
        self.assertIn("15:30", reply)

    def test_never_accuses_user(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(8, 0)
        reply = life.acknowledge_distraction("I need this for my study")
        self.assertNotIn("lie", reply.lower())
        self.assertNotIn("lying", reply.lower())
        self.assertEqual(1, life.state()["exceptions_today"])


class DailyStateAndRecoveryTests(unittest.TestCase):
    def test_daily_reset_at_wake_boundary(self) -> None:
        tmp = _tmpdir()
        life = _life(tmp)
        life.now_fn = lambda: _dt(8, 0)
        life.tick(_dt(8, 0))
        self.assertEqual("2026-08-19", life.state()["date"])
        # After 04:45 next morning — new routine day.
        self.assertNotEqual("2026-08-19", life.daily.day(_dt(4, 50, day=20)).date)

    def test_restart_recovery_no_duplicate_reminders(self) -> None:
        tmp = _tmpdir()
        life = _life(tmp)
        now = _dt(7, 0)
        events = life.tick(now)
        self.assertTrue(any(e.get("kind") == "reminder" for e in events))
        # Simulate restart: reload from the same memory dir.
        life2 = _life(tmp)
        events2 = life2.tick(now)
        self.assertEqual([], [e for e in events2 if e.get("kind") == "reminder"])

    def test_block_completion_tracking(self) -> None:
        life = _life()
        life.tick(_dt(8, 0))
        life.tick(_dt(9, 30))  # chemistry ends
        summary = life.daily.day_summary(_dt(9, 30).date())
        self.assertIn("chemistry_deep_study", summary["completed"])

    def test_profile_persistence_and_emptiness(self) -> None:
        tmp = _tmpdir()
        profile = PersonalProfile(tmp)
        self.assertIsNone(profile.get("name"))
        self.assertIsNone(profile.get("timezone"))
        profile.set("name", "Suraj")
        profile2 = PersonalProfile(tmp)
        self.assertEqual("Suraj", profile2.get("name"))

    def test_goals_and_events(self) -> None:
        tmp = _tmpdir()
        profile = PersonalProfile(tmp)
        goals = profile.__class__.__module__
        from jarvis.life.profile import GoalManager
        goal_manager = GoalManager(profile)
        goal = goal_manager.add("Improve chemistry preparation", priority="high",
                                related_blocks=["chemistry_deep_study"])
        self.assertEqual(0, goal["progress"])
        goal_manager.update_progress(goal["goal_id"], 40)
        self.assertEqual(40, goal_manager.all()[0]["progress"])
        events = SpecialEventManager(profile)
        events.add("2026-09-01", "Physics exam", importance="high")
        upcoming = events.upcoming(days=30, ref=datetime(2026, 8, 19).date())
        self.assertEqual(1, len(upcoming))

    def test_event_reminder_on_day(self) -> None:
        life = _life()
        life.events.add("2026-08-19", "Physics exam", importance="high")
        events = life.tick(_dt(6, 50))
        texts = [e["reminder"]["text"] for e in events if e.get("kind") == "reminder"]
        self.assertTrue(any("Physics exam" in t for t in texts))


class AcceleratedAcceptanceTests(unittest.TestCase):
    """Section 48: accelerated real-world acceptance with a shortened schedule."""

    def _compressed_routine(self, life: LifeAssistant) -> None:
        blocks = [
            {"id": "study1", "title": "Chemistry Deep Study", "start": "08:00", "end": "09:00",
             "category": "study", "subject": "chemistry", "monitor_distractions": True,
             "reminder": {"enabled": True, "pre_start_minutes": 5, "end_wrapup_minutes": 5}},
            {"id": "break1", "title": "Breakfast", "start": "09:00", "end": "09:15", "category": "meal"},
            {"id": "ent1", "title": "YouTube break", "start": "09:15", "end": "09:30",
             "category": "entertainment", "entertainment_allowed": True},
            {"id": "study2", "title": "Physics Deep Study", "start": "09:30", "end": "10:30",
             "category": "study", "subject": "physics", "monitor_distractions": True,
             "reminder": {"enabled": True, "pre_start_minutes": 5, "end_wrapup_minutes": 5}},
            {"id": "sleep1", "title": "Sleep", "start": "22:00", "end": "08:00", "category": "sleep"},
        ]
        life.routines.replace_blocks(blocks)

    def test_full_accelerated_day(self) -> None:
        life = _life()
        self._compressed_routine(life)
        seen: list[str] = []

        # 07:55 — pre-start reminder for chemistry.
        seen += [r["reminder"]["text"] for r in life.tick(_dt(7, 55)) if r.get("kind") == "reminder"]

        # 08:00 — study block starts, focus active.
        life.tick(_dt(8, 0))
        focus = life.focus.focus_state(_dt(8, 10))
        self.assertEqual("STUDY_ACTIVE", focus.mode)
        self.assertEqual("chemistry", focus.subject)

        # 08:15 — user opens entertainment video during study → distraction.
        monitor = life.distraction
        window = WindowObservation(app="chrome", title="Funny Cartoon Compilation - YouTube",
                                   url="https://www.youtube.com/watch?v=abc")
        base = monitor.evaluate(_dt(8, 15), window)
        self.assertEqual("OUT_OF_SCHEDULE", base.kind)
        monitor.escalate(_dt(8, 15), base, window)                                   # first sighting -> L1
        c = monitor.escalate(_dt(8, 15) + timedelta(seconds=95), base, window)       # L2 gentle reminder
        self.assertEqual(2, c.level)
        self.assertIn("chemistry", c.suggestion.lower())

        # 08:17 — user explains; accepted as allowed exception, no interference.
        reply = life.acknowledge_distraction("I'm watching a chemistry lecture", now=_dt(8, 17))
        self.assertIn("Understood", reply)
        self.assertEqual(1, life.state(_dt(8, 18))["exceptions_today"])

        # 08:55 — end-wrapup reminder.
        seen += [r["reminder"]["text"] for r in life.tick(_dt(8, 55)) if r.get("kind") == "reminder"]
        self.assertTrue(any("Five minutes left" in t for t in seen))

        # 08:59 — chemistry complete, breakfast next.
        seen += [r["reminder"]["text"] for r in life.tick(_dt(8, 59)) if r.get("kind") == "reminder"]
        self.assertTrue(any("complete" in t for t in seen))

        # 09:15 — entertainment break: no nagging about entertainment.
        r = monitor.evaluate(_dt(9, 20), WindowObservation(
            app="chrome", title="Funny Cartoon Compilation", url="https://www.youtube.com/watch?v=abc"))
        self.assertEqual("NOT_MONITORED", r.kind)

        # 09:30 — next study block starts after break.
        seen += [r["reminder"]["text"] for r in life.tick(_dt(9, 30)) if r.get("kind") == "reminder"]
        self.assertTrue(any("Physics" in t and "now" in t for t in seen))
        focus = life.focus.focus_state(_dt(9, 40))
        self.assertEqual("STUDY_ACTIVE", focus.mode)
        self.assertEqual("physics", focus.subject)

        # 22:00 — sleep mode, quiet.
        r = monitor.evaluate(_dt(22, 5), WindowObservation(app="chrome", url="https://x.com"))
        self.assertEqual("NOT_MONITORED", r.kind)
        focus = life.focus.focus_state(_dt(23, 0))
        self.assertEqual("SLEEP", focus.mode)

    def test_resource_efficiency_no_model_calls(self) -> None:
        """The ticker must be deterministic: no Groq/vision modules anywhere in the engine path."""
        import subprocess
        import sys
        code = (
            "import sys, tempfile\n"
            "from pathlib import Path\n"
            "from jarvis.life import LifeAssistant\n"
            "life = LifeAssistant(Path(tempfile.mkdtemp()), "
            "{'hydration': {'enabled': True}, 'reminders': {'enabled': True}, 'distraction': {'enabled': True}})\n"
            "life.tick()\n"
            "leaked = [m for m in ('jarvis.brain.groq_client', 'jarvis.brain.groq', 'jarvis.vision') if m in sys.modules]\n"
            "sys.exit(1 if leaked else 0)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=__file__.rsplit("tests", 1)[0],
            timeout=60,
        )
        self.assertEqual(0, proc.returncode, f"model modules leaked into the life engine path: {proc.stderr.strip()}")


class StateShapeTests(unittest.TestCase):
    def test_state_exposes_hud_fields(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(8, 0)
        state = life.state()
        for key in ("date", "current", "next", "focus", "distraction", "progress",
                    "hydration", "last_reminder", "overrides", "mode", "sleeping"):
            self.assertIn(key, state)
        self.assertEqual("chemistry_deep_study", state["current"]["id"])
        self.assertIn("remaining_seconds", state["current"])
        self.assertEqual("STUDY_ACTIVE", state["focus"]["mode"])
        self.assertEqual("breakfast", state["next"]["id"])
        self.assertEqual(24, state["progress"]["total"])

    def test_hud_sync_broadcast_event_flow(self) -> None:
        life = _life()
        life.now_fn = lambda: _dt(8, 0)
        got: list[dict] = []
        life.set_notifier(lambda events: got.extend(events))
        life.tick(_dt(8, 0))
        kinds = {e.get("kind") for e in got}
        self.assertIn("state", kinds)
        state_event = next(e for e in got if e.get("kind") == "state")
        self.assertEqual("chemistry_deep_study", state_event["state"]["current"]["id"])


if __name__ == "__main__":
    unittest.main()