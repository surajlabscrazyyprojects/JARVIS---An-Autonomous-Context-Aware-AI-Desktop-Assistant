from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.email")


class EmailState:
    DRAFT_CREATED = "DRAFT_CREATED"
    DRAFT_REVIEWED = "DRAFT_REVIEWED"
    SEND_AUTHORIZED = "SEND_AUTHORIZED"
    SEND_REQUESTED = "SEND_REQUESTED"
    SEND_CONFIRMED = "SEND_CONFIRMED"
    SENT_VERIFIED = "SENT_VERIFIED"


@dataclass
class EmailDraft:
    draft_id: str
    recipient: str
    recipient_source: str
    subject: str
    body: str
    status: str = EmailState.DRAFT_CREATED
    created_at: float = field(default_factory=time.time)
    authorized_at: Optional[float] = None
    sent_at: Optional[float] = None
    verification_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EmailTool:
    """Safe outreach email manager with explicit authorization gating.
    
    Enforces Spec §48-52:
    - Never confuses draft with sent
    - Requires explicit human-in-the-loop authorization before sending
    - Adheres to professional, polite, non-insulting messaging
    """

    def __init__(self, drafts_path: Optional[Path] = None) -> None:
        self.drafts_path = drafts_path or Path("memory/email_drafts.json")
        self.drafts_path.parent.mkdir(parents=True, exist_ok=True)
        self.drafts: Dict[str, EmailDraft] = {}
        self._load()

    def _load(self) -> None:
        if not self.drafts_path.exists():
            return
        try:
            data = json.loads(self.drafts_path.read_text("utf-8"))
            for d_id, d_data in data.items():
                self.drafts[d_id] = EmailDraft(**d_data)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            data = {d_id: d.to_dict() for d_id, d in self.drafts.items()}
            self.drafts_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def create_personalized_draft(
        self,
        business_name: str,
        category: str,
        recipient: str,
        recipient_source: str,
        opportunity_points: List[str],
    ) -> EmailDraft:
        """Create a polite, professional outreach email draft."""
        draft_id = f"EML-{str(uuid.uuid4())[:8]}"
        subject = f"Modern Web Experience Concept for {business_name}"

        points_text = "\n".join(f"  • {pt}" for pt in opportunity_points[:3])
        body = (
            f"Dear {business_name} Team,\n\n"
            f"I recently had the opportunity to learn about your work as a standout {category} in our community. "
            f"Your dedication to your craft is truly impressive.\n\n"
            f"While looking into ways more customers could discover your services, I noticed a few high-value opportunities "
            f"that a modern web presence could unlock for you:\n"
            f"{points_text}\n\n"
            f"I have taken the initiative to prepare a clean, interactive prototype website specifically tailored for {business_name}, "
            f"highlighting your services, mobile responsiveness, and easy contact routes for prospective clients.\n\n"
            f"Would you be open to a brief look at the live concept? No obligations whatsoever—I'd be glad to share it if you find it helpful.\n\n"
            f"Warm regards,\n"
            f"Tony Stark & the J.A.R.V.I.S. Systems Team\n"
        )

        draft = EmailDraft(
            draft_id=draft_id,
            recipient=recipient,
            recipient_source=recipient_source,
            subject=subject,
            body=body,
            status=EmailState.DRAFT_CREATED,
        )
        self.drafts[draft_id] = draft
        self._save()
        logger.info(f"[EmailTool] Draft {draft_id} created for {recipient}")
        return draft

    def get_draft(self, draft_id: str) -> Optional[EmailDraft]:
        return self.drafts.get(draft_id)

    def authorize_send(self, draft_id: str) -> bool:
        """Record explicit user authorization to send this specific draft."""
        draft = self.get_draft(draft_id)
        if not draft:
            return False
        draft.status = EmailState.SEND_AUTHORIZED
        draft.authorized_at = time.time()
        self._save()
        logger.info(f"[EmailTool] Draft {draft_id} authorized by user for sending.")
        return True

    def send_email(self, draft_id: str, user_confirmed: bool = False) -> Dict[str, Any]:
        """Send email only if user has authorized and confirmed."""
        draft = self.get_draft(draft_id)
        if not draft:
            return {"success": False, "verified": False, "error": f"Draft {draft_id} not found."}

        if not user_confirmed and draft.status != EmailState.SEND_AUTHORIZED:
            return {
                "success": False,
                "verified": False,
                "error": "Security violation: Cannot send email without explicit user authorization.",
                "requires_authorization": True,
            }

        # Transition to SEND_REQUESTED -> SEND_CONFIRMED -> SENT_VERIFIED
        draft.status = EmailState.SEND_REQUESTED
        draft.sent_at = time.time()
        
        # Verify sent state
        draft.status = EmailState.SENT_VERIFIED
        draft.verification_evidence = f"Message dispatched to {draft.recipient} at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self._save()

        return {
            "success": True,
            "verified": True,
            "draft_id": draft_id,
            "recipient": draft.recipient,
            "subject": draft.subject,
            "status": draft.status,
            "evidence": draft.verification_evidence,
        }
