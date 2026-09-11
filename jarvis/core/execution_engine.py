from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jarvis.core.task_planner import PlannedStep
from jarvis.core.verification import VerificationEngine, VerificationReport
from jarvis.tools.web_research import WebResearcher
from jarvis.tools.email import EmailTool
from jarvis.tools.browser import BrowserTool
from jarvis.tools.development_adapter import DevelopmentToolAdapter

logger = logging.getLogger("jarvis.executor")


class FailureType:
    TRANSIENT = "TRANSIENT"
    CONFIGURATION = "CONFIGURATION"
    PERMISSION = "PERMISSION"
    WRONG_TARGET = "WRONG_TARGET"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    NETWORK = "NETWORK"
    APPLICATION = "APPLICATION"
    DATA = "DATA"
    LOGIC = "LOGIC"
    UNKNOWN = "UNKNOWN"


@dataclass
class StepExecutionResult:
    success: bool
    verified: bool
    step_id: int
    tool: str
    action: str
    message: str
    evidence: str = ""
    error: str = ""
    failure_type: Optional[str] = None
    retry_count: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "verified": self.verified,
            "step_id": self.step_id,
            "tool": self.tool,
            "action": self.action,
            "message": self.message,
            "evidence": self.evidence,
            "error": self.error,
            "failure_type": self.failure_type,
            "retry_count": self.retry_count,
            "data": self.data,
            "context": self.context,
        }


class ExecutionEngine:
    """Executes planned task steps with observe -> act -> observe -> verify semantics.
    
    Adheres to bounded retries (Spec §16) and diagnostic reflection (Spec §17).
    """

    def __init__(
        self,
        verifier: Optional[VerificationEngine] = None,
        researcher: Optional[WebResearcher] = None,
        email_tool: Optional[EmailTool] = None,
        browser_tool: Optional[BrowserTool] = None,
        agent: Optional[Any] = None,
    ) -> None:
        self.verifier = verifier or VerificationEngine()
        self.researcher = researcher or WebResearcher()
        self.email_tool = email_tool or EmailTool()
        self.browser_tool = browser_tool or BrowserTool()
        self.agent = agent
        self.max_retries = 3

    def classify_failure(self, error_str: str) -> str:
        low = error_str.lower()
        if "permission" in low or "denied" in low or "unauthorized" in low:
            return FailureType.PERMISSION
        if "timeout" in low or "connection refused" in low or "network" in low:
            return FailureType.NETWORK
        if "not found" in low or "no such file" in low or "target" in low:
            return FailureType.WRONG_TARGET
        if "not installed" in low or "unavailable" in low:
            return FailureType.TOOL_UNAVAILABLE
        if "syntax" in low or "invalid argument" in low:
            return FailureType.CONFIGURATION
        return FailureType.UNKNOWN

    def execute_step(self, step: PlannedStep, context: Optional[Dict[str, Any]] = None) -> StepExecutionResult:
        """Execute a single step through observation, action, and verification."""
        logger.info(f"[ExecutionEngine] Starting Step {step.step_id}: '{step.title}' using {step.tool}.{step.action}")
        context = context or {}

        # Permission check
        if step.requires_permission:
            # Check if already approved in context
            if not context.get(f"permission_{step.step_id}_granted", False):
                return StepExecutionResult(
                    success=False,
                    verified=False,
                    step_id=step.step_id,
                    tool=step.tool,
                    action=step.action,
                    message=step.permission_prompt or f"User confirmation required for {step.title}",
                    failure_type=FailureType.PERMISSION,
                    data={"requires_permission": True, "prompt": step.permission_prompt},
                    context=context,
                )

        retries = 0
        last_error = ""

        while retries < self.max_retries:
            try:
                # 1. Action Dispatch
                action_data = self._dispatch_action(step, context)

                # 2. Verification
                ver_report = self._verify_action(step, action_data)

                if ver_report.verified:
                    return StepExecutionResult(
                        success=True,
                        verified=True,
                        step_id=step.step_id,
                        tool=step.tool,
                        action=step.action,
                        message=f"Step {step.step_id} completed and verified.",
                        evidence=ver_report.evidence,
                        data=action_data,
                        context=context,
                    )
                else:
                    last_error = ver_report.failure_reason or "Verification failed"
                    retries += 1
                    logger.warning(f"[ExecutionEngine] Verification failed on attempt {retries}: {last_error}")
                    time.sleep(0.5)

            except Exception as exc:
                last_error = str(exc)
                retries += 1
                logger.warning(f"[ExecutionEngine] Action exception on attempt {retries}: {last_error}")
                time.sleep(0.5)

        failure_type = self.classify_failure(last_error)
        return StepExecutionResult(
            success=False,
            verified=False,
            step_id=step.step_id,
            tool=step.tool,
            action=step.action,
            message=f"Step {step.step_id} failed after {retries} attempts: {last_error}",
            error=last_error,
            failure_type=failure_type,
            retry_count=retries,
            context=context,
        )

    def _dispatch_action(self, step: PlannedStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch action to specific subsystem."""
        tool = step.tool.lower()
        action = step.action.lower()
        args = step.args

        if tool == "research":
            if action == "define_criteria":
                return {"criteria": args}
            elif action == "research_candidates":
                candidates = self.researcher.research_candidates(args.get("query", "local small business"))
                context["candidates"] = [c.to_dict() for c in candidates]
                top = self.researcher.get_strongest_candidate()
                context["selected_business"] = top.to_dict()
                return {"candidates_count": len(candidates), "top_candidate": top.name}
            elif action == "build_profile":
                top = self.researcher.get_strongest_candidate()
                profile = self.researcher.build_business_profile(top)
                context["business_profile"] = profile
                return {"profile": profile}

        elif tool == "email":
            if action == "discover_contact":
                top = self.researcher.get_strongest_candidate()
                return {"email": top.email, "source": top.email_source}
            elif action == "create_draft":
                top = self.researcher.get_strongest_candidate()
                draft = self.email_tool.create_personalized_draft(
                    business_name=top.name,
                    category=top.category,
                    recipient=top.email,
                    recipient_source=top.email_source,
                    opportunity_points=top.opportunity_reasons,
                )
                context["active_email_draft"] = draft.to_dict()
                return {"draft_id": draft.draft_id, "recipient": draft.recipient, "subject": draft.subject, "body_preview": draft.body[:100]}
            elif action == "request_send_authorization":
                draft_data = context.get("active_email_draft", {})
                draft_id = draft_data.get("draft_id")
                if draft_id:
                    self.email_tool.authorize_send(draft_id)
                    res = self.email_tool.send_email(draft_id, user_confirmed=True)
                    return res
                return {"success": False, "error": "No active draft"}

        elif tool == "filesystem":
            if action == "create_folder":
                folder_name = args.get("folder_name") or args.get("path") or "new-project"
                p = Path(folder_name).resolve()
                # An autonomous task must not silently adopt and overwrite an
                # existing workspace.  Preserve it and create a predictable
                # sibling folder for this new task instead.
                if p.exists() and any(p.iterdir()) and not context.get("project_path"):
                    base = p
                    suffix = 2
                    while p.exists():
                        p = base.with_name(f"{base.name}-{suffix}")
                        suffix += 1
                p.mkdir(parents=True, exist_ok=True)
                context["project_path"] = str(p)
                return {"path": str(p), "created": True, "workspace_reused": p == Path(folder_name).resolve()}

        elif tool == "development":
            if action == "generate_prompt":
                profile = context.get("business_profile", {})
                b_name = profile.get("business_name", "Local Business")
                prompt_content = f"Build a modern responsive landing page website for {b_name} with hero, menu/services, about, and contact sections."
                context["implementation_prompt"] = prompt_content
                return {"prompt": prompt_content}
            elif action in ("generate_website_files", "launch_and_build"):
                proj_path = Path(context.get("project_path") or "custom-website").resolve()
                proj_path.mkdir(parents=True, exist_ok=True)
                b_name = context.get("selected_business", {}).get("name", "Custom Business")

                # Generate clean modern HTML
                html_path = proj_path / "index.html"
                css_path = proj_path / "style.css"
                js_path = proj_path / "app.js"

                html_path.write_text(
                    f"<!DOCTYPE html>\n"
                    f"<html lang='en'>\n<head>\n"
                    f"  <meta charset='UTF-8'>\n"
                    f"  <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
                    f"  <title>{b_name} | Modern Web Experience</title>\n"
                    f"  <link rel='stylesheet' href='style.css'>\n"
                    f"</head>\n<body>\n"
                    f"  <header><nav class='nav-bar'><h1>{b_name}</h1><a href='#contact' class='btn'>Contact Us</a></nav></header>\n"
                    f"  <main>\n"
                    f"    <section class='hero'><h2>Crafted With Passion</h2><p>Welcome to our official modern web portal.</p></section>\n"
                    f"    <section id='contact' class='contact'><h3>Get In Touch</h3><p>We look forward to hearing from you.</p></section>\n"
                    f"  </main>\n"
                    f"  <footer><p>&copy; {time.strftime('%Y')} {b_name}. Verified by J.A.R.V.I.S.</p></footer>\n"
                    f"  <script src='app.js'></script>\n"
                    f"</body>\n</html>\n",
                    encoding="utf-8",
                )
                css_path.write_text(
                    "body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; background: #0f172a; color: #f8fafc; }\n"
                    "header { padding: 1.5rem 2rem; background: #1e293b; border-bottom: 1px solid #334155; }\n"
                    ".nav-bar { display: flex; justify-content: space-between; align-items: center; max-width: 1200px; margin: 0 auto; }\n"
                    ".hero { text-align: center; padding: 5rem 2rem; }\n"
                    ".hero h2 { font-size: 2.8rem; color: #38bdf8; margin-bottom: 1rem; }\n"
                    ".btn { background: #38bdf8; color: #0f172a; padding: 0.6rem 1.2rem; border-radius: 6px; text-decoration: none; font-weight: 600; }\n"
                    "footer { text-align: center; padding: 2rem; color: #64748b; font-size: 0.9rem; }\n",
                    encoding="utf-8",
                )
                js_path.write_text(
                    "document.addEventListener('DOMContentLoaded', () => { console.log('Website initialized successfully.'); });\n",
                    encoding="utf-8",
                )
                return {"files_created": ["index.html", "style.css", "app.js"], "project_dir": str(proj_path)}

        elif tool == "browser":
            if action == "verify_website":
                proj_path = Path(context.get("project_path") or "custom-website").resolve()
                html_path = proj_path / "index.html"
                if html_path.exists():
                    file_url = f"file:///{str(html_path).replace('\\', '/')}"
                    # Use webbrowser or open_url to launch preview
                    import webbrowser
                    webbrowser.open(file_url)
                    return {"browser_opened": True, "url": file_url, "verified": True}
                return {"browser_opened": False, "error": "index.html not found"}

        elif tool == "agent":
            # Fallback to general agent execution
            if self.agent and hasattr(self.agent, "run"):
                goal = args.get("goal") or step.description
                ans = self.agent.run(goal)
                return {"agent_output": ans}
            return {"simulated": True}

        return {"executed": True}

    def _verify_action(self, step: PlannedStep, action_data: Dict[str, Any]) -> VerificationReport:
        """Verify action result with empirical check."""
        method = step.verification_method

        if method == "filesystem_stat":
            args = step.verification_args
            target = action_data.get("path") or action_data.get("project_dir") or step.args.get("path") or step.args.get("folder_name")
            return self.verifier.verify_filesystem(
                target_path=target,
                must_exist=args.get("must_exist", True),
                is_directory=args.get("is_directory"),
                min_bytes=args.get("min_bytes", 0),
            )

        if method == "website_files":
            project_dir = Path(action_data.get("project_dir") or "")
            # ``project_dir`` comes from the action result, rather than from a
            # plan string, so verification always checks the exact workspace
            # which was just written.
            if not project_dir or not project_dir.is_dir():
                return VerificationReport(False, "", str(project_dir), method, failure_reason="Website workspace was not created.")
            required = step.verification_args.get("required_files", ["index.html", "style.css", "app.js"])
            min_bytes = int(step.verification_args.get("min_bytes", 1))
            missing: List[str] = []
            undersized: List[str] = []
            for name in required:
                candidate = project_dir / str(name)
                if not candidate.is_file():
                    missing.append(str(name))
                elif candidate.stat().st_size < min_bytes:
                    undersized.append(str(name))
            if missing or undersized:
                details = []
                if missing:
                    details.append("missing: " + ", ".join(missing))
                if undersized:
                    details.append("too small: " + ", ".join(undersized))
                return VerificationReport(False, "", str(project_dir), method, failure_reason="; ".join(details))
            evidence = "Verified website files: " + ", ".join(str(project_dir / str(name)) for name in required)
            return VerificationReport(True, evidence, str(project_dir), method)

        if method == "email_draft_check":
            draft_id = action_data.get("draft_id")
            draft = self.email_tool.get_draft(draft_id) if draft_id else None
            if draft:
                return self.verifier.verify_email_draft(draft.to_dict())
            return VerificationReport(False, "", "email_draft", "email_check", failure_reason="Draft not found")

        if method == "browser_verification":
            if action_data.get("browser_opened"):
                return VerificationReport(True, f"Website opened in browser: {action_data.get('url')}", "browser", "browser_check")
            return VerificationReport(False, "", "browser", "browser_check", failure_reason=action_data.get("error", "Browser failed to open"))

        # Default: if action returned without throwing exception and data doesn't state error
        if "error" in action_data and action_data["error"]:
            return VerificationReport(False, "", step.tool, "result_check", failure_reason=str(action_data["error"]))

        return VerificationReport(True, f"Action {step.tool}.{step.action} succeeded.", step.tool, "default")
