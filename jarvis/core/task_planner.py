from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from jarvis.ai.openrouter import ModelRole
from jarvis.ai.providers import ProviderRouter

logger = logging.getLogger("jarvis.planner")


@dataclass
class PlannedStep:
    step_id: int
    title: str
    description: str
    tool: str  # "research", "agent", "browser", "development", "email", "filesystem"
    action: str
    args: Dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    verification_method: str = "none"
    verification_args: Dict[str, Any] = field(default_factory=dict)
    requires_permission: bool = False
    permission_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskPlan:
    goal: str
    summary: str
    steps: List[PlannedStep] = field(default_factory=list)
    completion_conditions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "summary": self.summary,
            "steps": [s.to_dict() for s in self.steps],
            "completion_conditions": self.completion_conditions,
            "metadata": self.metadata,
        }


class TaskGapDetector:
    """Detects missing steps required to genuinely complete a goal without inventing unrelated scope."""

    WEBSITE_MANDATORY_CRITERIA = [
        "project_directory_exists",
        "core_files_exist",
        "build_or_server_verified",
        "browser_result_inspected",
    ]

    OUTREACH_MANDATORY_CRITERIA = [
        "target_business_identified",
        "verified_contact_route_found",
        "personalized_draft_created",
        "explicit_send_authorization_obtained",
    ]

    def detect_gaps(self, goal: str, completed_step_titles: List[str]) -> List[str]:
        gaps = []
        low_goal = goal.lower()
        completed_low = [s.lower() for s in completed_step_titles]

        is_website = any(k in low_goal for k in ("website", "web site", "site", "web app", "landing page", "homepage"))
        is_outreach = any(k in low_goal for k in ("outreach", "email", "contact", "find business", "small business"))

        if is_website:
            if not any("folder" in s or "directory" in s or "project" in s for s in completed_low):
                gaps.append("Project workspace folder creation")
            if not any("build" in s or "code" in s or "generate" in s for s in completed_low):
                gaps.append("Implementation coding and file generation")
            if not any("verify" in s or "browser" in s or "inspect" in s for s in completed_low):
                gaps.append("Browser preview verification of completed site")

        if is_outreach:
            if not any("research" in s or "candidate" in s or "profile" in s for s in completed_low):
                gaps.append("Business candidate research and verification")
            if not any("draft" in s or "email" in s for s in completed_low):
                gaps.append("Personalized outreach email drafting")

        return gaps


class TaskPlanner:
    """Multi-step task planner using OpenRouter DEEP_REASONING models."""

    def __init__(self, provider_router: Optional[ProviderRouter] = None) -> None:
        self.router = provider_router or ProviderRouter()
        self.gap_detector = TaskGapDetector()

    def plan_task(self, goal: str, context: Optional[Dict[str, Any]] = None) -> TaskPlan:
        """Decompose goal into an executable multi-step plan with verification criteria."""
        # Check standard workflow templates first for rapid deterministic execution
        template = self._match_workflow_template(goal, context)
        if template:
            return template

        # Dynamic planning via DEEP_REASONING model
        prompt = (
            f"You are the master task planner for J.A.R.V.I.S., an autonomous computer agent.\n"
            f"Goal: '{goal}'\n"
            f"Context: {json.dumps(context or {}, indent=2)}\n\n"
            f"Generate a strict JSON execution plan with actionable computer steps.\n"
            f"Tools available: 'research', 'agent', 'browser', 'development', 'email', 'filesystem'.\n"
            f"Output ONLY JSON with this format:\n"
            f"{{\n"
            f'  "summary": "Concise summary",\n'
            f'  "completion_conditions": ["condition1", "condition2"],\n'
            f'  "steps": [\n'
            f"    {{\n"
            f'      "step_id": 1,\n'
            f'      "title": "Short title",\n'
            f'      "description": "What this step does",\n'
            f'      "tool": "filesystem",\n'
            f'      "action": "create_folder",\n'
            f'      "args": {{"path": "..."}},\n'
            f'      "verification_method": "filesystem_stat",\n'
            f'      "verification_args": {{"must_exist": true}}\n'
            f"    }}\n"
            f"  ]\n"
            f"}}"
        )

        try:
            res = self.router.chat(
                messages=[{"role": "user", "content": prompt}],
                role=ModelRole.PLANNING,
                temperature=0.2,
                max_tokens=2048,
                is_foreground=True,
            )
            content = res.get("response", {}).get("choices", [{}])[0].get("message", {}).get("content", "")
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                steps = [
                    PlannedStep(
                        step_id=s.get("step_id", idx + 1),
                        title=s.get("title", f"Step {idx + 1}"),
                        description=s.get("description", ""),
                        tool=s.get("tool", "agent"),
                        action=s.get("action", "execute"),
                        args=s.get("args", {}),
                        expected_output=s.get("expected_output", ""),
                        verification_method=s.get("verification_method", "none"),
                        verification_args=s.get("verification_args", {}),
                        requires_permission=bool(s.get("requires_permission", False)),
                        permission_prompt=s.get("permission_prompt", ""),
                    )
                    for idx, s in enumerate(data.get("steps", []))
                ]
                return TaskPlan(
                    goal=goal,
                    summary=data.get("summary", "Custom task plan"),
                    steps=steps,
                    completion_conditions=data.get("completion_conditions", []),
                )
        except Exception as exc:
            logger.error(f"[TaskPlanner] Dynamic planning failed: {exc}")

        # Fallback to general execution step
        return TaskPlan(
            goal=goal,
            summary=f"Execute goal: {goal}",
            steps=[
                PlannedStep(
                    step_id=1,
                    title=f"Execute goal",
                    description=goal,
                    tool="agent",
                    action="run_agent",
                    args={"goal": goal},
                    verification_method="none",
                )
            ],
            completion_conditions=[f"Goal completed: {goal}"],
        )

    def _match_workflow_template(self, goal: str, context: Optional[Dict[str, Any]]) -> Optional[TaskPlan]:
        low = goal.lower()

        # Business Outreach + Website Workflow (Spec §43-55, §86)
        if any(k in low for k in (
            "find a small business", "find me a small business", "find me a small local business",
            "find a local small business", "find a local business", "find me a local business",
            "find a business that would benefit", "business that would benefit",
            "benefit from a website", "outreach and website",
        )):
            return TaskPlan(
                goal=goal,
                summary="Research local business with weak web presence, prepare outreach email, and build modern website project.",
                completion_conditions=[
                    "target_business_verified",
                    "public_contact_verified",
                    "email_draft_prepared",
                    "website_project_directory_created",
                    "website_implementation_verified",
                    "browser_preview_verified",
                ],
                steps=[
                    PlannedStep(
                        step_id=1,
                        title="Define candidate selection criteria",
                        description="Identify local small businesses with poor/missing websites and clear customer value.",
                        tool="research",
                        action="define_criteria",
                        args={"category": "local_service", "signal": "missing_or_outdated_site"},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=2,
                        title="Research and rank public business candidates",
                        description="Query public directories and maps for candidate businesses lacking modern websites.",
                        tool="research",
                        action="research_candidates",
                        args={"query": "local small business cafe bakery"},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=3,
                        title="Build detailed target business profile",
                        description="Extract services, location, hours, branding signals, and website opportunity points.",
                        tool="research",
                        action="build_profile",
                        args={},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=4,
                        title="Discover and verify legitimate public contact email",
                        description="Locate official contact channel; never guess or synthesize unverified addresses.",
                        tool="email",
                        action="discover_contact",
                        args={},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=5,
                        title="Draft personalized professional outreach email",
                        description="Draft respectful email highlighting website opportunities without being insulting.",
                        tool="email",
                        action="create_draft",
                        args={},
                        verification_method="email_draft_check",
                    ),
                    PlannedStep(
                        step_id=6,
                        title="Request explicit authorization before sending",
                        description="Present recipient, source, and exact email draft to user for explicit approval.",
                        tool="email",
                        action="request_send_authorization",
                        args={},
                        requires_permission=True,
                        permission_prompt="I have drafted the outreach email. Would you like me to send it to the business contact?",
                    ),
                    PlannedStep(
                        step_id=7,
                        title="Create website project directory",
                        description="Create local development workspace for the business website.",
                        tool="filesystem",
                        action="create_folder",
                        args={"folder_name": "business-website-project"},
                        verification_method="filesystem_stat",
                        verification_args={"must_exist": True, "is_directory": True},
                    ),
                    PlannedStep(
                        step_id=8,
                        title="Generate implementation requirements and prompt",
                        description="Create tailored specification for OpenCode/development tool with business branding.",
                        tool="development",
                        action="generate_prompt",
                        args={},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=9,
                        title="Launch development tool and build website",
                        description="Initialize workspace and generate clean HTML/CSS/JS or modern React frontend.",
                        tool="development",
                        action="launch_and_build",
                        args={},
                        verification_method="none",
                    ),
                    PlannedStep(
                        step_id=10,
                        title="Inspect and verify completed website in browser",
                        description="Start local dev preview or open index.html in browser, verifying layout and responsiveness.",
                        tool="browser",
                        action="verify_website",
                        args={},
                        verification_method="browser_verification",
                    ),
                ],
            )

        # Website Build Only
        if any(k in low for k in ("build a website", "create a website", "make a website", "build a site")):
            target_name = "custom-website"
            words = low.split()
            if "for" in words:
                idx = words.index("for")
                if idx + 1 < len(words):
                    target_name = "-".join(words[idx + 1:idx + 3]) + "-website"

            return TaskPlan(
                goal=goal,
                summary=f"Build and verify website for {target_name}.",
                completion_conditions=[
                    "project_directory_created",
                    "website_files_created",
                    "browser_preview_verified",
                ],
                steps=[
                    PlannedStep(
                        step_id=1,
                        title=f"Create project folder {target_name}",
                        description="Set up clean workspace directory for the website files.",
                        tool="filesystem",
                        action="create_folder",
                        args={"folder_name": target_name},
                        verification_method="filesystem_stat",
                        verification_args={"must_exist": True, "is_directory": True},
                    ),
                    PlannedStep(
                        step_id=2,
                        title="Generate website code and assets",
                        description="Create index.html, style.css, and app.js with responsive design and modern styling.",
                        tool="development",
                        action="generate_website_files",
                        args={"project_name": target_name},
                        verification_method="website_files",
                        verification_args={
                            "required_files": ["index.html", "style.css", "app.js"],
                            "min_bytes": 100,
                        },
                    ),
                    PlannedStep(
                        step_id=3,
                        title="Open and verify website in browser",
                        description="Open browser, inspect page render, check console for errors, and verify responsiveness.",
                        tool="browser",
                        action="verify_website",
                        args={"project_name": target_name},
                        verification_method="browser_verification",
                    ),
                ],
            )

        return None
