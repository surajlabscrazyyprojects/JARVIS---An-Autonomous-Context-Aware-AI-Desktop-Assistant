from __future__ import annotations

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path

from jarvis.automation import TaskExecutor
from jarvis.models import ActionStep, Plan, ToolResult
from jarvis.runtime import Capability, CapabilityRegistry, EventStore, TaskStore


class TaskStoreTests(unittest.TestCase):
    def test_interrupted_task_requires_reverification_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.json")
            task = store.create("Open Notepad", total_steps=1)
            store.transition(task["task_id"], "planning")
            store.transition(task["task_id"], "executing")
            store.checkpoint(task["task_id"], 1)

            restarted = TaskStore(Path(directory) / "tasks.json")
            recovered = restarted.recover_interrupted()

            self.assertEqual([task["task_id"]], [item["task_id"] for item in recovered])
            self.assertEqual("recovery_required", restarted.get(task["task_id"])["status"])
            self.assertEqual(1, restarted.get(task["task_id"])["current_step"])

    def test_illegal_terminal_transition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.json")
            task = store.create("Do work", total_steps=1)
            with self.assertRaises(ValueError):
                store.transition(task["task_id"], "completed_verified")


class EventStoreTests(unittest.TestCase):
    def test_events_are_ordered_and_filterable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events = EventStore(Path(directory) / "events.jsonl")
            events.append("TASK_STARTED", task_id="one")
            events.append("TASK_COMPLETED", task_id="one", status="success")
            events.append("TASK_STARTED", task_id="two")
            self.assertEqual(["TASK_STARTED", "TASK_COMPLETED"], [item["event"] for item in events.recent(task_id="one")])


class FailingComputer:
    def open_app(self, _name: str) -> ToolResult:
        return ToolResult(False, False, {}, "launch blocked", 1, verification_method="fake")

    def observe(self):
        return type("Observation", (), {"screen_summary": None})()


class NoRepairPlanner:
    def repair_plan(self, *_args):
        return []


class ExecutorTruthfulnessTests(unittest.TestCase):
    def test_unverified_action_never_completes_task(self) -> None:
        registry = CapabilityRegistry()
        registry.register(Capability("open_app", "fake open"))
        executor = TaskExecutor(
            FailingComputer(),
            terminal=None,  # type: ignore[arg-type]
            filesystem=None,
            vision=None,  # type: ignore[arg-type]
            planner=NoRepairPlanner(),  # type: ignore[arg-type]
            observer=None,  # type: ignore[arg-type]
            max_retries=0,
            logger=logging.getLogger("test"),
            capabilities=registry,
        )
        plan = Plan("Open test app", "", "neutral", False, "", [ActionStep("open_app", "Launch test app", {"name": "test"})])
        observed: list[ToolResult] = []

        async def progress(_kind: str, _message: str) -> None:
            return None

        async def on_step(_number: int, _step: ActionStep, result: ToolResult) -> None:
            observed.append(result)

        result = asyncio.run(executor.execute(plan, progress, on_step))
        self.assertFalse(result.success)
        self.assertIn("could not verify", result.message.lower())
        self.assertEqual(1, len(observed))
        self.assertFalse(observed[0].verified)

    def test_ui_input_requires_and_uses_explicit_observation(self) -> None:
        class InputComputer:
            def type_text(self, _text: str) -> ToolResult:
                return ToolResult(
                    True,
                    False,
                    {"message": "Input delivered; outcome unverified."},
                    None,
                    1,
                    verification_method="input_delivery_only",
                )

            def verify(self, verify: dict) -> ToolResult:
                self.last_verify = verify
                return ToolResult(True, True, {"message": "Window title confirmed."}, None, 1, verification_method="active_window_title_check")

            def observe(self):
                return type("Observation", (), {"screen_summary": None})()

        registry = CapabilityRegistry()
        registry.register(Capability("type_text", "type text"))
        computer = InputComputer()
        executor = TaskExecutor(
            computer,  # type: ignore[arg-type]
            terminal=None,  # type: ignore[arg-type]
            filesystem=None,
            vision=None,  # type: ignore[arg-type]
            planner=NoRepairPlanner(),  # type: ignore[arg-type]
            observer=None,  # type: ignore[arg-type]
            max_retries=0,
            logger=logging.getLogger("test"),
            capabilities=registry,
        )
        plan = Plan(
            "Enter a value",
            "",
            "neutral",
            False,
            "",
            [ActionStep("type_text", "Enter a value", {"text": "hello"}, {"type": "active_window_contains", "text": "Example"})],
        )

        async def progress(_kind: str, _message: str) -> None:
            return None

        result = asyncio.run(executor.execute(plan, progress))
        self.assertTrue(result.success)
        self.assertEqual({"type": "active_window_contains", "text": "Example"}, computer.last_verify)

    def test_ui_input_without_observation_cannot_complete_task(self) -> None:
        class InputComputer:
            def type_text(self, _text: str) -> ToolResult:
                return ToolResult(True, False, {"message": "Input delivered; outcome unverified."}, None, 1, verification_method="input_delivery_only")

            def observe(self):
                return type("Observation", (), {"screen_summary": None})()

        registry = CapabilityRegistry()
        registry.register(Capability("type_text", "type text"))
        executor = TaskExecutor(
            InputComputer(),  # type: ignore[arg-type]
            terminal=None,  # type: ignore[arg-type]
            filesystem=None,
            vision=None,  # type: ignore[arg-type]
            planner=NoRepairPlanner(),  # type: ignore[arg-type]
            observer=None,  # type: ignore[arg-type]
            max_retries=0,
            logger=logging.getLogger("test"),
            capabilities=registry,
        )
        plan = Plan("Enter a value", "", "neutral", False, "", [ActionStep("type_text", "Enter a value", {"text": "hello"})])

        async def progress(_kind: str, _message: str) -> None:
            return None

        result = asyncio.run(executor.execute(plan, progress))
        self.assertFalse(result.success)
        self.assertIn("could not verify", result.message.lower())
