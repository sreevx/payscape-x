"""API contract for the AI Decision Agent (Part 8).

GET  /api/v1/decisions/{transaction_id}              — generate (idempotent)
                                                       the auditable decision
POST /api/v1/decisions/{decision_id}/approve         — PENDING -> APPROVED
POST /api/v1/decisions/{decision_id}/reject          — PENDING -> REJECTED
                                                       (optional reason)

The response is a RECOMMENDATION ONLY: approving or rejecting merely
records the merchant's decision. Nothing in Part 8 executes a refund,
payment, message or any external action. `decision_source` tells the UI
whether the recommendation came from the LLM or the deterministic
fallback; `decision_confidence` is always computed deterministically from
verified inputs (an LLM confidence value is an explanation signal only).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlternativeActionItem(BaseModel):
    """One alternative action the merchant could consider instead."""

    model_config = ConfigDict(from_attributes=True)

    action: str
    reason: str


class DecisionResponse(BaseModel):
    """The complete auditable decision for one transaction."""

    decision_id: str
    transaction_id: str
    # LLM | DETERMINISTIC_FALLBACK
    decision_source: str
    # DO_NOTHING | RECOVER_ROOT_CAUSE | REFUND_OR_CONTAIN | HUMAN_REVIEW
    recommended_action: str
    reason: str
    decision_confidence: float
    evidence_confidence: float
    evidence_ids: list[str]
    event_ids: list[str]
    simulation_id: Optional[str] = None
    alternatives: list[AlternativeActionItem]
    human_approval_required: bool
    # PENDING | APPROVED | REJECTED
    approval_status: str
    rejection_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict = {}


class ApproveDecisionRequest(BaseModel):
    """Body of POST /api/v1/decisions/{decision_id}/approve."""

    note: Optional[str] = Field(
        None, max_length=500, description="Optional merchant note (audit trail)."
    )


class RejectDecisionRequest(BaseModel):
    """Body of POST /api/v1/decisions/{decision_id}/reject."""

    reason: Optional[str] = Field(
        None, max_length=1000, description="Optional rejection reason."
    )