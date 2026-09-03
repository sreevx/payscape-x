"""Outcome Engine domain models (Part 5).

Deterministic structures produced by the outcome decision engine. The
engine answers one question:

    "Did the business transaction actually succeed?"

That is deliberately NOT the same as "was the payment successful?" The
engine classifies the reconstructed business journey into exactly one of
FULFILLED / AT_RISK / FAILED / UNVERIFIABLE using the Part 3 journey, the
Part 4 evidence report and the Part 4 consistency report.

Everything here is computed — never LLM-derived, never random, never an
ML probability. Same inputs produce the same outcome, confidence, reasons
and evidence references every time.
"""

from dataclasses import dataclass, field
from typing import Optional

OUTCOME_FULFILLED = "FULFILLED"
OUTCOME_AT_RISK = "AT_RISK"
OUTCOME_FAILED = "FAILED"
OUTCOME_UNVERIFIABLE = "UNVERIFIABLE"

ALL_OUTCOMES = (
    OUTCOME_FULFILLED,
    OUTCOME_AT_RISK,
    OUTCOME_FAILED,
    OUTCOME_UNVERIFIABLE,
)

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"

# Deterministic base confidence per outcome, before documented
# adjustments (see engine.py + docs/architecture.md for the methodology).
OUTCOME_BASE_CONFIDENCE: dict[str, float] = {
    OUTCOME_FULFILLED: 0.97,
    OUTCOME_FAILED: 0.95,
    OUTCOME_AT_RISK: 0.60,
    OUTCOME_UNVERIFIABLE: 0.45,
}
# Lower base when UNVERIFIABLE is caused by contradictory records.
UNVERIFIABLE_CONTRADICTION_CONFIDENCE = 0.35

# Confidence hard floor/ceiling so a score never looks like a perfect
# statistical certainty.
CONFIDENCE_FLOOR = 0.05
CONFIDENCE_CEILING = 0.99


@dataclass
class OutcomeReason:
    """One auditable reason for the outcome.

    `code` and `message` are concise facts derived from records — never
    free-form chain-of-thought. `event_ids` and `evidence_ids` trace the
    reason back to the exact records that support it.
    """

    code: str
    message: str
    severity: str
    rule_id: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ConfidenceAdjustment:
    """One documented, deterministic confidence adjustment."""

    signal: str
    delta: float
    note: str


@dataclass
class RuleTraceStep:
    """One rule evaluation in the decision trace (ordered by priority)."""

    rule_id: str
    name: str
    priority: int
    outcome: str
    applied: bool
    note: str


@dataclass
class OutcomeResult:
    """The full deterministic outcome classification for one transaction."""

    transaction_id: str
    outcome: str
    confidence: float
    primary_reason: OutcomeReason
    reasons: list[OutcomeReason] = field(default_factory=list)
    supporting_evidence_ids: list[str] = field(default_factory=list)
    supporting_event_ids: list[str] = field(default_factory=list)
    blocking_evidence_ids: list[str] = field(default_factory=list)
    consistency_status: Optional[str] = None
    evidence_completeness: Optional[float] = None
    rule_trace: list[RuleTraceStep] = field(default_factory=list)
    confidence_adjustments: list[ConfidenceAdjustment] = field(default_factory=list)