import asyncio
import os
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

from jarvis.core.task_orchestrator import TaskOrchestrator, TaskStatus
from jarvis.core.instruction_classifier import InstructionClassifier, InstructionType
from jarvis.core.verification import VerificationEngine
from jarvis.tools.web_research import WebResearcher
from jarvis.tools.email import EmailTool


def test_instruction_classification():
    classifier = InstructionClassifier()
    goal = "Build website for artisan bakery"

    assert classifier.classify("stop", goal) == InstructionType.TASK_CANCELLATION
    assert classifier.classify("cancel this task", goal) == InstructionType.TASK_CANCELLATION
    assert classifier.classify("pause for now", goal) == InstructionType.TASK_PAUSE
    assert classifier.classify("how is it going?", goal) == InstructionType.STATUS_REQUEST
    assert classifier.classify("what is the progress?", goal) == InstructionType.STATUS_REQUEST
    assert classifier.classify("make the header darker", goal) == InstructionType.TASK_UPDATE
    assert classifier.classify("change the font to modern sans", goal) == InstructionType.TASK_UPDATE
    print("✓ test_instruction_classification passed")


def test_web_research_and_email():
    researcher = WebResearcher()
    candidates = researcher.research_candidates()
    assert len(candidates) >= 2
    top = researcher.get_strongest_candidate()
    assert top.name
    assert top.email
    assert "@" in top.email

    email_tool = EmailTool()
    draft = email_tool.create_personalized_draft(
        business_name=top.name,
        category=top.category,
        recipient=top.email,
        recipient_source=top.email_source,
        opportunity_points=top.opportunity_reasons,
    )
    assert draft.draft_id
    assert draft.recipient == top.email
    assert draft.status == "DRAFT_CREATED"

    # Gated send without authorization should fail
    fail_res = email_tool.send_email(draft.draft_id, user_confirmed=False)
    assert not fail_res["verified"]

    # Authorized send should succeed
    email_tool.authorize_send(draft.draft_id)
    send_res = email_tool.send_email(draft.draft_id, user_confirmed=True)
    assert send_res["verified"]
    print("✓ test_web_research_and_email passed")


def test_verification_engine():
    # Verify existing directory
    v = VerificationEngine.verify_filesystem(".", must_exist=True, is_directory=True)
    assert v.verified

    # Verify non-existent file
    v_missing = VerificationEngine.verify_filesystem("non_existent_file_xyz.txt", must_exist=True)
    assert not v_missing.verified

    print("✓ test_verification_engine passed")


async def test_task_orchestrator_execution():
    orchestrator = TaskOrchestrator()
    task = orchestrator.accept_goal("Build a website for Apex Coffee Roasters")
    assert task.task_id
    assert task.total_steps >= 3

    # Execute task loop
    progress_log = []
    def on_prog(p):
        progress_log.append(p)

    final_task = await orchestrator.execute_task_loop(task.task_id, on_progress=on_prog)
    assert final_task.status == TaskStatus.COMPLETED
    assert len(final_task.completed_steps) >= 3
    print("✓ test_task_orchestrator_execution passed")


if __name__ == "__main__":
    test_instruction_classification()
    test_web_research_and_email()
    test_verification_engine()
    asyncio.run(test_task_orchestrator_execution())
    print("\nALL CORE TESTS PASSED SUCCESSFULLY!")
