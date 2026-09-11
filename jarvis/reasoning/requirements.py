from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from jarvis.context import ContextFusionEngine, CurrentContextSnapshot


@dataclass
class RequirementDiscoveryResult:
    goal: str
    known: List[str] = field(default_factory=list)
    observable: List[str] = field(default_factory=list)
    inferable: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    required_confirmation: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RequirementDiscoveryEngine:
    def __init__(self, fusion: ContextFusionEngine) -> None:
        self.fusion = fusion

    def discover(self, goal: str, context: CurrentContextSnapshot | None = None) -> RequirementDiscoveryResult:
        context = context or self.fusion.snapshot(goal)
        result = RequirementDiscoveryResult(goal=goal, known=list(context.known))
        result.observable.extend(self._observable_sources(context))
        result.inferable.extend(self._inferable_context(context))
        result.unknown.extend(self._unknown_for_goal(context))
        result.required_confirmation.extend(self._confirmation_for_goal(context))
        result.questions.extend(self._questions_for_goal(context))
        result.assumptions.extend(self._assumptions(context))
        return result

    def _observable_sources(self, context: CurrentContextSnapshot) -> List[str]:
        observable = []
        for name in ("browser", "project", "application"):
            source = context.sources.get(name, {})
            if source.get("availability") == "available":
                observable.append(name)
        return observable

    def _inferable_context(self, context: CurrentContextSnapshot) -> List[str]:
        if context.referenced_entity.get("type") == "browser_page":
            return ["the user is referring to the authorized current browser page"]
        return []

    def _unknown_for_goal(self, context: CurrentContextSnapshot) -> List[str]:
        if context.user_intent == "build_website":
            unknown = ["design direction", "primary website goal", "required business features"]
            if context.referenced_entity.get("type") != "browser_page":
                unknown.insert(0, "referenced business identity")
            return unknown
        return []

    def _confirmation_for_goal(self, context: CurrentContextSnapshot) -> List[str]:
        if context.user_intent == "build_website":
            return ["permission to create a project and start a development tool"]
        return []

    def _questions_for_goal(self, context: CurrentContextSnapshot) -> List[str]:
        if context.user_intent != "build_website":
            return []
        questions = []
        if context.referenced_entity.get("type") != "browser_page":
            questions.append("Which business or page should I use as the reference?")
        questions.extend([
            "What direction should the design take: premium, modern minimal, cozy local, or experimental?",
            "What is the main goal of the site: discovery, reservations, ordering, or a simple online presence?",
            "Do you need reservations, online ordering, or another specific feature?",
        ])
        return questions[:3]

    def _assumptions(self, context: CurrentContextSnapshot) -> List[str]:
        if context.user_intent == "build_website":
            return ["No business facts are assumed beyond authorized context sources."]
        return []
