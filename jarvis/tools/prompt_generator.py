from __future__ import annotations

from typing import Any, Dict


class TaskPromptGenerator:
    def generate(self, goal: str, context: Dict[str, Any], requirements: Dict[str, Any], tool: str) -> str:
        browser = context.get("browser", {})
        business = context.get("referenced_entity", {})
        return "\n".join([
            "PROJECT OBJECTIVE",
            goal,
            "",
            "CONTEXT",
            f"Development tool: {tool}",
            f"Referenced page title: {browser.get('title') or 'Unavailable'}",
            f"Referenced page URL: {browser.get('url') or 'Unavailable'}",
            f"Referenced entity basis: {business.get('basis') or 'Unavailable'}",
            "",
            "REQUIREMENTS",
            f"Known: {requirements.get('known', [])}",
            f"Observable: {requirements.get('observable', [])}",
            f"Confirmed: {requirements.get('confirmed', [])}",
            f"Unknown: {requirements.get('unknown', [])}",
            f"Assumptions: {requirements.get('assumptions', ['None'])}",
            "",
            "QUALITY REQUIREMENTS",
            "Use responsive, accessible, semantic UI. Do not invent business facts or assets.",
            "Verify the build, tests, and primary user flow before reporting completion.",
            "Clearly report blockers and unavailable inputs.",
            "",
            "ACCEPTANCE CRITERIA",
            "The project builds successfully, renders the intended site, and documents any unverified requirement.",
        ])
