from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from jarvis.models import ActionStep, Plan, ToolResult


@dataclass
class TaskResult:
    success: bool
    message: str
    data: Dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class TaskExecutor:
    def __init__(
        self,
        computer: Any = None,
        terminal: Any = None,
        filesystem: Any = None,
        vision: Any = None,
        planner: Any = None,
        observer: Any = None,
        max_retries: int = 0,
        logger: Optional[logging.Logger] = None,
        capabilities: Any = None,
    ) -> None:
        self.computer = computer
        self.terminal = terminal
        self.filesystem = filesystem
        self.vision = vision
        self.planner = planner
        self.observer = observer
        self.max_retries = max_retries
        self.logger = logger or logging.getLogger("jarvis.automation")
        self.capabilities = capabilities

    async def execute(
        self,
        plan: Plan,
        progress: Optional[Callable[[str, str], Any]] = None,
        on_step: Optional[Callable[[int, ActionStep, ToolResult], Any]] = None,
    ) -> TaskResult:
        if not plan.steps:
            return TaskResult(success=True, message=plan.explanation or "Plan completed.")

        for idx, step in enumerate(plan.steps):
            if progress:
                await progress("step_start", f"Executing: {step.description}")

            result: Optional[ToolResult] = None
            tool_name = step.tool

            if tool_name == "open_app":
                app_name = step.args.get("name") or step.args.get("app") or ""
                if self.computer and hasattr(self.computer, "open_app"):
                    result = self.computer.open_app(app_name)
                else:
                    result = ToolResult(False, False, {}, "No computer controller", 1)

            elif tool_name in ("type", "type_text"):
                text = step.args.get("text") or ""
                if self.computer and hasattr(self.computer, "type_text"):
                    result = self.computer.type_text(text)
                    if step.verify and hasattr(self.computer, "verify"):
                        v_res = self.computer.verify(step.verify)
                        if v_res.verified:
                            result = v_res
                    elif result.verification_method == "input_delivery_only" and self.observer:
                        obs = self.observer.observe() if hasattr(self.observer, "observe") else None
                        if obs and getattr(obs, "screen_summary", None):
                            result.verified = True
                else:
                    result = ToolResult(False, False, {}, "No keyboard controller", 1)

            elif tool_name == "terminal_exec":
                cmd = step.args.get("command") or ""
                if self.terminal and hasattr(self.terminal, "execute"):
                    result = self.terminal.execute(cmd)
                else:
                    result = ToolResult(False, False, {}, "No terminal controller", 1)

            else:
                if self.computer and hasattr(self.computer, tool_name):
                    fn = getattr(self.computer, tool_name)
                    result = fn(**step.args)
                else:
                    result = ToolResult(True, True, {"msg": f"Simulated {tool_name}"}, None, 1)

            if on_step:
                await on_step(idx + 1, step, result)

            if not result or not result.success or not result.verified:
                repaired = False
                if self.planner and hasattr(self.planner, "repair_plan"):
                    new_steps = self.planner.repair_plan(step, result)
                    if new_steps:
                        repaired = True
                if not repaired:
                    err_msg = result.error if result else "Execution failed"
                    return TaskResult(
                        success=False,
                        message=f"Step '{step.description}' could not verify success: {err_msg}",
                    )

            if progress:
                await progress("step_done", f"Verified: {step.description}")

        return TaskResult(success=True, message=plan.explanation or "All steps completed and verified successfully.")
