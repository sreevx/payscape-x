"""AI Decision Agent domain models (Part 8).

The Decision Agent answers ONE question about an already-analyzed
transaction:

    "Given the verified evidence, business outcome, failure chain, impact
     and simulation results, what should the merchant do next?"

Architecture rule — AI reasons, CODE VERIFIES:

- The agent reasons ONLY over the structured facts produced by Parts 1-7
  (a `DecisionContext`). It never receives raw database dumps and can never
  invent evidence, events, amounts or customer information.
- The agent may ONLY recommend one of the four registered actions. An LLM
  that returns anything else (or hallucinated ids, unsupported simulation
  references or malformed output) is rejected and the deterministic
  fallback takes over.
- Part 5 stays the sole authority for the outcome classification, Part 6
  for failure/impact, Part 7 for simulation results. Nothing here
  recalculates or mutates them.
- Part 8 is ONLY: REASON -> RECOMMEND -> WAIT FOR HUMAN. Approving a
  decision records merchant approval — it never executes a refund, payment,
  message or any external action.
- Confidence is computed deterministically from verified inputs. An LLM
  confidence value (if any) is kept only as an explanation signal and is
  never used as the system confidence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import DecisionAction, DecisionApprovalStatus, DecisionSource

# Recommended-action registry (mirrors DecisionAction — plain constants so
# dataclasses stay light; the enums are used by the ORM + API layer).
ACTION_DO_NOTHING = DecisionAction.DO_NOTHING.value
ACTION_RECOVER_ROOT_CAUSE = DecisionAction.RECOVER_ROOT_CAUSE.value
ACTION_REFUND_OR_CONTAIN = DecisionAction.REFUND_OR_CONTAIN.value
ACTION_HUMAN_REVIEW = DecisionAction.HUMAN_REVIEW.value

ALL_ACTIONS = (
    ACTION_DO_NOTHING,
    ACTION_RECOVER_ROOT_CAUSE,
    ACTION_REFUND_OR_CONTAIN,
    ACTION_HUMAN_REVIEW,
)

SOURCE_LLM = DecisionSource.LLM.value
SOURCE_FALLBACK = DecisionSource.DETERMINISTIC_FALLBACK.value

APPROVAL_PENDING = DecisionApprovalStatus.PENDING.value
APPROVAL_APPROVED = DecisionApprovalStatus.APPROVED.value
APPROVAL_REJECTED = DecisionApprovalStatus.REJECTED.value

ALL_APPROVAL_STATUSES = (
    APPROVAL_PENDING,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
)

# Root-cause kinds that a deterministic remedy could recover. Recovery is
# only ever recommended when the Part 7 simulation actually resolves one of
# these failure nodes — never on kind alone.
RECOVERABLE_ROOT_CAUSE_KINDS = frozenset({
    "INVENTORY_ALLOCATION_FAILED",
    "INVENTORY_RESERVATION_EXPIRED",
    "FULFILLMENT_NOT_CREATED",
    "FULFILLMENT_FAILED",
    "NO_FULFILLMENT",
})

# Recovery interventions offered by the Part 7 lab, in preference order.
RECOVERY_INTERVENTIONS = ("ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT")

# Deterministic confidence bounds (documented in docs/architecture.md).
DECISION_CONFIDENCE_FLOOR = 0.10
DECISION_CONFIDENCE_CEILING = 0.99


@dataclass(frozen=True)
class AlternativeAction:
    """One alternative the merchant could consider instead."""

    action: str
    reason: str


@dataclass(frozen=True)
class SimulationFact:
    """One deterministic Part 7 simulation result used by the agent."""

    intervention_type: str
    status: str                 # SIMULATED | NOT_APPLICABLE | NOT_EFFECTIVE | NOT_SUPPORTED
    simulation_id: str
    simulated_outcome: str
    delta_impact_score: float
    resolved_failure_kinds: tuple[str, ...] = ()
    remaining_failure_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionContext:
    """Structured, verified facts the agent may reason over.

    Built once per request from the real Part 3-7 pipeline. This is the
    ONLY input the LLM provider receives — no raw events, no free text, no
    database access.
    """

    transaction_id: str
    # Part 5 — the sole authority for the outcome.
    outcome: str
    outcome_confidence: float
    primary_reason_code: str
    primary_reason_message: str
    # Part 4.
    consistency_status: str
    # Part 6.
    compound_failure_detected: bool
    compound_failure_severity: str
    # Part 4 (rest).
    evidence_claims: tuple[tuple[str, str, str, str, float], ...] = ()  # (id, category, claim, strength, confidence)
    evidence_gaps: tuple[tuple[str, str], ...] = ()                     # (event_type, note)
    contradictions: tuple[tuple[str, str, str], ...] = ()               # (type, rule_id, explanation)
    failure_chain: tuple[tuple[str, str, str], ...] = ()                # (kind, stage, label)
    root_cause_kinds: tuple[str, ...] = ()
    impact_score: float = 0.0
    impact_scope: str = "SINGLE_TRANSACTION"
    affected_transactions: int = 1
    # Part 7.
    simulations: tuple[SimulationFact, ...] = ()
    comparison: tuple[tuple[str, int], ...] = ()                        # (intervention_type, rank)
    # Deterministic flags derived from the records above.
    payment_captured: bool = False
    refund_recorded: bool = False
    customer_impacting: bool = False
    evidence_confidence: float = 0.0
    # The full verified event id set of the reconstructed journey, so an
    # LLM-claimed event id can be validated against the real records.
    event_ids: tuple[str, ...] = ()

    @property
    def all_evidence_ids(self) -> frozenset[str]:
        return frozenset(item[0] for item in self.evidence_claims)

    @property
    def all_event_ids(self) -> frozenset[str]:
        return frozenset(self.event_ids)

    @property
    def simulation_ids(self) -> frozenset[str]:
        return frozenset(item.simulation_id for item in self.simulations)

    @property
    def applicable_simulations(self) -> tuple[SimulationFact, ...]:
        return tuple(item for item in self.simulations if item.status == "SIMULATED")


@dataclass(frozen=True)
class DecisionProposal:
    """What a provider (LLM or fallback) proposes — before assembly.

    `llm_confidence` is an explanation signal only; the assembled
    `decision_confidence` is always computed deterministically from the
    verified inputs and never taken from the proposal.
    """

    recommended_action: str
    reason: str
    evidence_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    simulation_id: Optional[str] = None
    alternatives: tuple[AlternativeAction, ...] = ()
    fallback_rule_id: Optional[str] = None
    llm_confidence: Optional[float] = None


@dataclass
class DecisionResult:
    """The complete auditable decision for one transaction."""

    decision_id: str
    transaction_id: str
    decision_source: str               # LLM | DETERMINISTIC_FALLBACK
    recommended_action: str
    reason: str
    decision_confidence: float
    evidence_confidence: float
    evidence_ids: list[str]
    event_ids: list[str]
    simulation_id: Optional[str]
    alternatives: list[AlternativeAction]
    human_approval_required: bool
    approval_status: str               # PENDING | APPROVED | REJECTED
    rejection_reason: Optional[str]
    decided_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    metadata: dict = field(default_factory=dict)