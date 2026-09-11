"""End-to-end acceptance workflow for the JARVIS Autonomous Task Operating System.

Exercises the Spec §86 acceptance path end-to-end against the real
TaskOrchestrator:
    research -> candidate ranking -> profile -> contact discovery
    -> personalized email draft -> EXPLICIT authorization gate
    -> website project -> generated files -> browser verification
"""
import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from jarvis.core.task_orchestrator import TaskOrchestrator, TaskStatus


async def run_acceptance() -> None:
    orchestrator = TaskOrchestrator()
    goal = (
        "Find me a small business that would genuinely benefit from a better website, "
        "research it, prepare a professional outreach email, and build the website for it."
    )

    task = orchestrator.accept_goal(goal)
    print(f"Task {task.task_id}: '{task.goal}'")
    print(f"  planned steps: {task.total_steps}")
    for s in task.remaining_steps:
        print(f"    [{s['step_id']}] {s['title']} (tool={s['tool']}.{s['action']} perm={s.get('requires_permission', False)})")
    assert task.total_steps >= 10, "acceptance workflow must be a real multi-step plan"

    # --- phase 1: run until a permission gate appears ---------------------
    permission_seen = {"step": None, "prompt": ""}

    def on_perm(payload) -> None:
        permission_seen["step"] = payload.get("step_id")
        permission_seen["prompt"] = payload.get("prompt", "")

    task = await orchestrator.execute_task_loop(task.task_id, on_permission_required=on_perm)
    print(f"  first loop ended in status: {task.status.value} (completed {len(task.completed_steps)})")
    assert task.status == TaskStatus.WAITING_FOR_PERMISSION, "email send must require explicit authorization"
    assert permission_seen["prompt"], "permission gate must carry a user prompt"
    assert task.remaining_steps and task.remaining_steps[0].get("requires_permission"), "the gated step must be the email send"

    # --- user explicitly authorizes the draft ------------------------------------
    print(f"  user is shown: {permission_seen['prompt']}")
    orchestrator.grant_permission(task.task_id, True)
    print("  -> user authorized the outreach email")

    # --- phase 2: resume and execute to completion ---------------------------------
    task = await orchestrator.execute_task_loop(task.task_id, on_permission_required=on_perm)
    assert task.status == TaskStatus.COMPLETED, f"expected COMPLETED, got {task.status}"

    assert len(task.completed_steps) >= task.total_steps >= 10
    titles = [s.get("title", "") for s in task.completed_steps]
    joined = " | ".join(titles).lower()
    assert "business" in joined and "email" in joined and "project" in joined and ("verified" in joined or "browser" in joined)

    # The verified artifacts must really exist on disk (no hallucination).
    from jarvis.core.verification import VerificationEngine
    proj_rel = [a.get("path") for a in task.artifacts if a.get("path")]
    if not proj_rel:
        proj_rel = [next((s["args"].get("folder_name") for s in task.completed_steps if s.get("args", {}).get("folder_name")), "")]
    for p in proj_rel:
        if p:
            rep = VerificationEngine.verify_filesystem(p, must_exist=True, is_directory=True)
            assert rep.verified, f"project directory missing: {p}"

    print("=== ACCEPTANCE PASSED — task completed_verified ===")
    print(orchestrator.journal.generate_status_summary(task.task_id, goal=goal))


if __name__ == "__main__":
    asyncio.run(run_acceptance())