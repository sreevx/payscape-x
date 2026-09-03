"""Read API contract for the Simulation Lab (Part 7).

GET  /api/v1/simulations/{transaction_id}       — baseline + every
                                                  intervention's simulated
                                                  result + ranked comparison
POST /api/v1/simulations/{transaction_id}/run   — run ONE intervention
GET  /api/v1/simulations/{transaction_id}/compare — ranked comparison table

Every result is labelled SIMULATED: a deterministic scenario estimate over
the observed records, never an actual outcome, a prediction or a guarantee.
Responses are read-only — nothing in the lab modifies the transaction.
"""

from pydantic import BaseModel, ConfigDict


class InterventionItem(BaseModel):
    """One intervention the merchant can compare against the baseline."""

    model_config = ConfigDict(from_attributes=True)

    intervention_type: str
    label: str
    description: str


class FailureRefItem(BaseModel):
    """A deterministic failure reference (kind + label + producing rule)."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    label: str
    rule_id: str


class RiskRefItem(BaseModel):
    """A deterministic risk reference introduced by the simulated world."""

    model_config = ConfigDict(from_attributes=True)

    claim: str
    rule_id: str
    classification: str   # OBSERVED | DERIVED | POTENTIAL


class SimulationBaselineItem(BaseModel):
    """The observed (ACTUAL) state every intervention is compared against."""

    transaction_id: str
    outcome: str          # FULFILLED | AT_RISK | FAILED | UNVERIFIABLE
    confidence: float
    consistency_status: str | None = None
    compound_failure_detected: bool
    severity: str         # LOW | MEDIUM | HIGH | CRITICAL
    impact_score: float
    impact_scope: str     # SINGLE_TRANSACTION | MULTI_TRANSACTION
    affected_transactions: int
    root_causes: list[FailureRefItem]
    event_ids: list[str]
    evidence_ids: list[str]


class SimulationResultItem(BaseModel):
    """The deterministic simulation of ONE intervention."""

    model_config = ConfigDict(from_attributes=True)

    simulation_id: str
    transaction_id: str
    # SIMULATED | NOT_APPLICABLE | NOT_EFFECTIVE | NOT_SUPPORTED
    status: str
    reason: str
    intervention: InterventionItem
    baseline_outcome: str
    baseline_confidence: float
    simulated_outcome: str
    simulated_confidence: float
    baseline_impact_score: float
    simulated_impact_score: float
    delta_impact_score: float   # simulated - baseline (negative = improvement)
    resolved_failures: list[FailureRefItem]
    remaining_failures: list[FailureRefItem]
    new_risks: list[RiskRefItem]
    assumptions: list[str]
    event_ids: list[str]
    evidence_ids: list[str]
    rule_ids: list[str]
    metadata: dict = {}


class CompareItem(BaseModel):
    """One row of the deterministic comparison table (ranked)."""

    model_config = ConfigDict(from_attributes=True)

    rank: int
    intervention_type: str
    label: str
    status: str
    simulated_outcome: str
    simulated_impact_score: float
    delta_impact_score: float
    remaining_failure_count: int
    assumption_count: int


class SimulationReport(BaseModel):
    """Baseline + every intervention simulation + ranked comparison."""

    transaction_id: str
    baseline: SimulationBaselineItem
    interventions: list[SimulationResultItem]
    comparison: list[CompareItem]


class RunSimulationRequest(BaseModel):
    """Body of POST /api/v1/simulations/{transaction_id}/run."""

    intervention: str
