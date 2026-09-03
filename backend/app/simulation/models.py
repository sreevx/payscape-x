"""Simulation Lab domain models (Part 7).

Deterministic structures produced by the Simulation Engine. The engine
answers one question about an already-analyzed transaction:

    "What could have been done differently?"

Every result is labelled SIMULATED and is a *scenario estimate* computed by
deterministic business rules over the real journey / evidence / consistency
/ outcome / compound-failure / impact records. It is never:

- an actual outcome, historical fact or guaranteed future result
- an ML prediction or financial forecast

Three spellings keep the semantics honest:

- the BASELINE describes the observed records (ACTUAL)
- the SIMULATED view describes one counterfactual intervention
- an intervention that cannot act deterministically reports
  NOT_APPLICABLE / NOT_EFFECTIVE / NOT_SUPPORTED instead of pretending

IDs are deterministic (uuid5 over the transaction + intervention), repeated
runs with the same database state produce byte-identical JSON, and the
simulation is strictly read-only — it never modifies payment, order,
inventory, refund or webhook records.
"""

from dataclasses import dataclass, field
from typing import Optional

# Result statuses of one simulated intervention.
SIM_STATUS_SIMULATED = "SIMULATED"
SIM_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
SIM_STATUS_NOT_EFFECTIVE = "NOT_EFFECTIVE"
SIM_STATUS_NOT_SUPPORTED = "NOT_SUPPORTED"

ALL_SIM_STATUSES = (
    SIM_STATUS_SIMULATED,
    SIM_STATUS_NOT_APPLICABLE,
    SIM_STATUS_NOT_EFFECTIVE,
    SIM_STATUS_NOT_SUPPORTED,
)

# Registry order for the interventions offered by the lab.
INTERVENTION_DO_NOTHING = "DO_NOTHING"
INTERVENTION_RETRY_FULFILLMENT = "RETRY_FULFILLMENT"
INTERVENTION_ALTERNATIVE_INVENTORY = "ALTERNATIVE_INVENTORY"
INTERVENTION_SUBSTITUTE_PRODUCT = "SUBSTITUTE_PRODUCT"
INTERVENTION_REFUND = "REFUND"
INTERVENTION_HUMAN_REVIEW = "HUMAN_REVIEW"

ALL_INTERVENTIONS = (
    INTERVENTION_DO_NOTHING,
    INTERVENTION_RETRY_FULFILLMENT,
    INTERVENTION_ALTERNATIVE_INVENTORY,
    INTERVENTION_SUBSTITUTE_PRODUCT,
    INTERVENTION_REFUND,
    INTERVENTION_HUMAN_REVIEW,
)


@dataclass(frozen=True)
class InterventionDef:
    """One intervention the merchant can compare against the baseline."""

    intervention_type: str
    label: str
    description: str


@dataclass
class FailureRef:
    """A deterministic failure reference (kind + label + producing rule)."""

    kind: str
    label: str
    rule_id: str


@dataclass
class RiskRef:
    """A deterministic risk / consequence reference in the simulated world."""

    claim: str
    rule_id: str
    classification: str  # OBSERVED | DERIVED | POTENTIAL


@dataclass
class SimulationBaseline:
    """The observed (ACTUAL) state every intervention is compared against."""

    transaction_id: str
    outcome: str                  # FULFILLED | AT_RISK | FAILED | UNVERIFIABLE
    confidence: float
    consistency_status: Optional[str]
    compound_failure_detected: bool
    severity: str                 # LOW | MEDIUM | HIGH | CRITICAL
    impact_score: float
    impact_scope: str
    affected_transactions: int
    root_causes: list[FailureRef] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """The deterministic simulation of ONE intervention."""

    simulation_id: str
    transaction_id: str
    status: str                   # SIMULATED | NOT_APPLICABLE | NOT_EFFECTIVE |
                                  # NOT_SUPPORTED
    reason: str
    intervention: InterventionDef
    baseline_outcome: str
    baseline_confidence: float
    simulated_outcome: str
    simulated_confidence: float
    baseline_impact_score: float
    simulated_impact_score: float
    delta_impact_score: float     # simulated - baseline (negative = improvement)
    resolved_failures: list[FailureRef] = field(default_factory=list)
    remaining_failures: list[FailureRef] = field(default_factory=list)
    new_risks: list[RiskRef] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CompareItem:
    """One row of the deterministic comparison table (ranked)."""

    rank: int
    intervention_type: str
    label: str
    status: str
    simulated_outcome: str
    simulated_impact_score: float
    delta_impact_score: float
    remaining_failure_count: int
    assumption_count: int


@dataclass
class SimulationReport:
    """Baseline + every intervention simulation + ranked comparison."""

    transaction_id: str
    baseline: SimulationBaseline
    interventions: list[SimulationResult] = field(default_factory=list)
    comparison: list[CompareItem] = field(default_factory=list)
