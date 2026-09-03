"""Read API contract for the Outcome Engine (Part 5).

The response is deterministic: one of FULFILLED / AT_RISK / FAILED /
UNVERIFIABLE with a confidence score, auditable reasons and full
traceability back to the exact evidence items and events that support it.

Reasons are concise facts derived from records (code + message), never
free-form chain-of-thought. Confidence is a deterministic record-strength
score, not an LLM probability and not fake statistical certainty.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class OutcomeReason(BaseModel):
    """One auditable reason for the outcome."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    severity: str  # LOW | MEDIUM | HIGH
    rule_id: str
    event_ids: list[str]
    evidence_ids: list[str]


class ConfidenceAdjustment(BaseModel):
    """One documented deterministic confidence adjustment."""

    model_config = ConfigDict(from_attributes=True)

    signal: str
    delta: float
    note: str


class RuleTraceStep(BaseModel):
    """One rule evaluation in the decision trace (ordered by priority)."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    name: str
    priority: int
    outcome: str
    applied: bool
    note: str


class OutcomeResponse(BaseModel):
    """The deterministic business-outcome classification for a transaction."""

    transaction_id: str
    # FULFILLED | AT_RISK | FAILED | UNVERIFIABLE
    outcome: str
    confidence: float
    primary_reason: OutcomeReason
    reasons: list[OutcomeReason]
    supporting_evidence_ids: list[str]
    supporting_event_ids: list[str]
    blocking_evidence_ids: list[str]
    consistency_status: Optional[str] = None
    evidence_completeness: Optional[float] = None
    rule_trace: list[RuleTraceStep]
    confidence_adjustments: list[ConfidenceAdjustment]