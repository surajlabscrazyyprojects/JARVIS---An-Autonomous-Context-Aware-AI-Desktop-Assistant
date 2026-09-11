from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jarvis.core.task_planner import TaskPlanner, TaskPlan, PlannedStep
from jarvis.core.task_journal import TaskJournal
from jarvis.core.verification import VerificationEngine
from jarvis.core.instruction_classifier import InstructionClassifier, InstructionType
from jarvis.core.execution_engine import ExecutionEngine, StepExecutionResult, FailureType

logger = logging.getLogger("jarvis.orchestrator")


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    READY = "READY"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


@dataclass
class Task:
    task_id: str
    goal: str
    request_id: str = ""
    parent_task_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: TaskStatus = TaskStatus.CREATED
    priority: str = "NORMAL"  # "CRITICAL", "HIGH", "NORMAL", "BACKGROUND"
    current_step: int = 0
    total_steps: int = 0
    completed_steps: List[Dict[str, Any]] = field(default_factory=list)
    remaining_steps: List[Dict[str, Any]] = field(default_factory=list)
    blocked_steps: List[Dict[str, Any]] = field(default_factory=list)
    completion_conditions: List[str] = field(default_factory=list)
    requirements: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    tools_used: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    permissions: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    retries: int = 0
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    next_action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class TaskOrchestrator:
    """Persistent Autonomous Task Operating System for JARVIS.
    
    Owns the entire objective from understanding, planning, continuous step-by-step
    execution, verification, error adaptation, to final verified completion.
    """

    def __init__(
        self,
        planner: Optional[TaskPlanner] = None,
        executor: Optional[ExecutionEngine] = None,
        journal: Optional[TaskJournal] = None,
        classifier: Optional[InstructionClassifier] = None,
    ) -> None:
        self.planner = planner or TaskPlanner()
        self.executor = executor or ExecutionEngine()
        self.journal = journal or TaskJournal()
        self.classifier = classifier or InstructionClassifier()
        self.tasks: Dict[str, Task] = {}
        self.active_task_id: Optional[str] = None
        self._cancellation_requested: Dict[str, bool] = {}
        self._pause_requested: Dict[str, bool] = {}
        self._recover_interrupted_tasks()

    def _recover_interrupted_tasks(self) -> None:
        """Crash recovery: restore any tasks saved before sudden shutdown."""
        for cp_file in self.journal.checkpoint_dir.glob("*.json"):
            try:
                cp = self.journal.load_latest_checkpoint(cp_file.stem)
                if cp and cp.status in (TaskStatus.EXECUTING.value, TaskStatus.PLANNING.value, TaskStatus.VERIFYING.value):
                    task = Task(
                        task_id=cp.task_id,
                        goal=cp.goal,
                        status=TaskStatus.PAUSED,  # Safe paused state until user resumes
                        current_step=cp.step_index,
                        completed_steps=cp.completed_steps,
                        remaining_steps=cp.remaining_steps,
                        context=cp.context_snapshot,
                        artifacts=cp.artifacts,
                    )
                    self.tasks[task.task_id] = task
                    logger.info(f"[TaskOrchestrator] Recovered interrupted task {task.task_id}: '{task.goal}'")
            except Exception as e:
                logger.warning(f"[TaskOrchestrator] Failed recovering checkpoint {cp_file}: {e}")

    def accept_goal(
        self,
        goal: str,
        request_id: str = "",
        parent_task_id: Optional[str] = None,
        priority: str = "NORMAL",
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Initialize and plan a new persistent task."""
        task_id = f"TSK-{str(uuid.uuid4())[:8]}"
        task = Task(
            task_id=task_id,
            goal=goal,
            request_id=request_id or f"REQ-{int(time.time()) % 10000:04d}",
            parent_task_id=parent_task_id,
            status=TaskStatus.PLANNING,
            priority=priority,
            context=initial_context or {},
        )
        self.tasks[task_id] = task
        self.active_task_id = task_id

        # Generate plan
        plan: TaskPlan = self.planner.plan_task(goal, context=task.context)
        task.completion_conditions = plan.completion_conditions
        task.remaining_steps = [s.to_dict() for s in plan.steps]
        task.total_steps = len(plan.steps)
        task.next_action = task.remaining_steps[0] if task.remaining_steps else None
        task.status = TaskStatus.READY
        task.updated_at = time.time()

        # Checkpoint initial state
        self._save_checkpoint(task)
        logger.info(f"[TaskOrchestrator] Accepted goal '{goal}' as {task_id} with {task.total_steps} planned steps.")
        return task

    def _save_checkpoint(self, task: Task) -> None:
        self.journal.create_checkpoint(
            task_id=task.task_id,
            step_index=task.current_step,
            goal=task.goal,
            status=task.status.value,
            completed_steps=task.completed_steps,
            remaining_steps=task.remaining_steps,
            context_snapshot=task.context,
            artifacts=task.artifacts,
        )

    def pause_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.PAUSED
            self._pause_requested[task_id] = True
            self._save_checkpoint(self.tasks[task_id])
            logger.info(f"[TaskOrchestrator] Task {task_id} paused.")
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.READY
            self._pause_requested[task_id] = False
            self.active_task_id = task_id
            logger.info(f"[TaskOrchestrator] Task {task_id} resumed from step {task.current_step}.")
            return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.CANCELLED
            self._cancellation_requested[task_id] = True
            if self.active_task_id == task_id:
                self.active_task_id = None
            self._save_checkpoint(task)
            logger.info(f"[TaskOrchestrator] Task {task_id} cancelled.")
            return True
        return False

    def grant_permission(self, task_id: str, granted: bool = True) -> None:
        """Grant permission for a pending step."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.remaining_steps:
                next_step = task.remaining_steps[0]
                step_id = next_step.get("step_id", 1)
                task.context[f"permission_{step_id}_granted"] = granted
                if granted:
                    task.status = TaskStatus.READY
                else:
                    task.status = TaskStatus.BLOCKED
                    task.errors.append("Permission denied by user")

    def handle_user_instruction(self, text: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Classify and apply real-time user speech against the active task (Spec §6, §7)."""
        target_id = task_id or self.active_task_id
        active_task = self.tasks.get(target_id) if target_id else None
        goal = active_task.goal if active_task else ""

        inst_type = self.classifier.classify(text, active_task_goal=goal)
        logger.info(f"[TaskOrchestrator] User instruction '{text}' classified as {inst_type.value}")

        if inst_type == InstructionType.TASK_CANCELLATION:
            if active_task:
                self.cancel_task(active_task.task_id)
                return {"action": "cancelled", "message": "Task cancelled as requested, sir."}
            return {"action": "none", "message": "No active task to cancel."}

        elif inst_type == InstructionType.TASK_PAUSE:
            if active_task:
                self.pause_task(active_task.task_id)
                return {"action": "paused", "message": "Task paused, sir. Let me know when you would like to continue."}
            return {"action": "none", "message": "No active task to pause."}

        elif inst_type == InstructionType.STATUS_REQUEST:
            if active_task:
                summary = self.journal.generate_status_summary(active_task.task_id, goal=active_task.goal)
                return {"action": "status", "message": summary}
            return {"action": "status", "message": "All systems nominal. No background tasks currently active."}

        elif inst_type == InstructionType.TASK_UPDATE:
            if active_task:
                # Update task requirements without restarting from zero (Spec §84)
                active_task.requirements.setdefault("user_updates", []).append(text)
                active_task.context["latest_user_update"] = text
                logger.info(f"[TaskOrchestrator] Task {active_task.task_id} updated with: '{text}'")
                return {"action": "updated", "message": f"Understood, sir. Integrating '{text}' into the current objective."}
            return {"action": "none", "message": "No active task to update."}

        elif inst_type == InstructionType.TASK_REPLACEMENT:
            if active_task:
                self.cancel_task(active_task.task_id)
            new_task = self.accept_goal(text)
            return {"action": "replaced", "task_id": new_task.task_id, "message": f"Scrapping the previous project. Starting: '{text}'."}

        return {"action": "proceed", "type": inst_type.value}

    async def execute_task_loop(
        self,
        task_id: str,
        on_progress: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_permission_required: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Task:
        """The persistent execution loop (Spec §5).
        
        Continues executing until the goal is verified complete, user cancels/pauses,
        or permission is required.
        """
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        logger.info(f"[TaskOrchestrator] Running loop for task {task_id}: '{task.goal}'")

        while task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.PAUSED):
            # Check external interrupts
            if self._cancellation_requested.get(task_id):
                task.status = TaskStatus.CANCELLED
                break
            if self._pause_requested.get(task_id):
                task.status = TaskStatus.PAUSED
                break

            # Check if all steps completed
            if not task.remaining_steps:
                # Run gap detection before declaring completion (Spec §4, §64)
                completed_titles = [s.get("title", "") for s in task.completed_steps]
                gaps = self.planner.gap_detector.detect_gaps(task.goal, completed_titles)
                if gaps:
                    logger.info(f"[TaskOrchestrator] Gap detector identified {len(gaps)} missing steps: {gaps}")
                    # Dynamically append missing steps
                    for gap_title in gaps:
                        gap_step = PlannedStep(
                            step_id=len(task.completed_steps) + len(task.remaining_steps) + 1,
                            title=gap_title,
                            description=f"Address missing requirement: {gap_title}",
                            tool="development" if "build" in gap_title.lower() else "browser",
                            action="execute",
                        )
                        task.remaining_steps.append(gap_step.to_dict())
                    continue

                # Goal is genuinely complete!
                task.status = TaskStatus.COMPLETED
                self._save_checkpoint(task)
                if on_progress:
                    on_progress({
                        "task_id": task.task_id,
                        "status": "completed",
                        "message": f"Goal completed and verified: '{task.goal}'",
                    })
                break

            # Execute next step
            next_step_dict = task.remaining_steps[0]
            step = PlannedStep(
                step_id=next_step_dict.get("step_id", task.current_step + 1),
                title=next_step_dict.get("title", ""),
                description=next_step_dict.get("description", ""),
                tool=next_step_dict.get("tool", "agent"),
                action=next_step_dict.get("action", "execute"),
                args=next_step_dict.get("args", {}),
                verification_method=next_step_dict.get("verification_method", "none"),
                verification_args=next_step_dict.get("verification_args", {}),
                requires_permission=bool(next_step_dict.get("requires_permission", False)),
                permission_prompt=next_step_dict.get("permission_prompt", ""),
            )

            # Check if step was already verified (Spec §36: Never repeat completed work)
            if self.journal.is_step_completed(task.task_id, step.description):
                logger.info(f"[TaskOrchestrator] Step '{step.title}' was already verified in journal. Skipping.")
                task.completed_steps.append(task.remaining_steps.pop(0))
                task.current_step += 1
                continue

            task.status = TaskStatus.EXECUTING
            task.current_step = step.step_id
            self.journal.record_step(task.task_id, step.step_id, step.description, "ACTIVE")

            if on_progress:
                on_progress({
                    "task_id": task.task_id,
                    "status": "executing",
                    "step": step.title,
                    "progress": f"{len(task.completed_steps)}/{task.total_steps}",
                })

            # Check for permission gating (e.g. sending unsolicited email)
            if step.requires_permission and not task.context.get(f"permission_{step.step_id}_granted"):
                task.status = TaskStatus.WAITING_FOR_PERMISSION
                self._save_checkpoint(task)
                if on_permission_required:
                    on_permission_required({
                        "task_id": task.task_id,
                        "step_id": step.step_id,
                        "prompt": step.permission_prompt or f"Authorize {step.title}?",
                    })
                # Yield loop until permission arrives
                break

            # Dispatch step to ExecutionEngine
            res: StepExecutionResult = self.executor.execute_step(step, context=task.context)
            # Persist any context produced/consumed by the step onto the live task.
            if res.context and res.context is not task.context:
                task.context.update(res.context)

            if res.verified:
                task.completed_steps.append(task.remaining_steps.pop(0))
                task.verification_results.append(res.to_dict())
                self.journal.record_step(task.task_id, step.step_id, step.description, "VERIFIED", evidence=res.evidence)
                self._save_checkpoint(task)
                logger.info(f"[TaskOrchestrator] Step {step.step_id} verified: {res.evidence}")
            else:
                task.status = TaskStatus.RECOVERING
                task.errors.append(res.error)
                self.journal.record_step(task.task_id, step.step_id, step.description, "FAILED", error=res.error)
                logger.warning(f"[TaskOrchestrator] Step {step.step_id} failed. Error: {res.error}")

                # If permission blocked, stop
                if res.failure_type == FailureType.PERMISSION:
                    task.status = TaskStatus.WAITING_FOR_PERMISSION
                    break
                else:
                    # Non-fatal: retry limit reached, ask user or fail safely
                    task.status = TaskStatus.FAILED
                    break

            # Brief non-blocking yield between steps
            await asyncio.sleep(0.3)

        return task
