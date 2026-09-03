"""Read API contract for the Consequence / Impact Engine (Part 6).

Consequences are strictly labelled OBSERVED / DERIVED / POTENTIAL — the
engine never presents a potential consequence as an observed fact, and
never turns absence of evidence into impact. The impact score is a
transparent deterministic score (formula + per-component breakdown
returned in the payload), NOT a prediction and NOT a financial loss claim.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConsequenceItem(BaseModel):
    """One downstream consequence of the failure."""

    model_config = ConfigDict(from_attributes=True)

    consequence_id: str
    category: str
    claim: str
    classification: str        # OBSERVED | DERIVED | POTENTIAL
    rule_id: str
    event_ids: list[str]
    evidence_ids: list[str]
    metadata: dict = {}


class AffectedTransactionItem(BaseModel):
    """Another transaction hit by the same underlying condition."""

    transaction_id: str
    order_id: str
    external_order_id: str
    scenario_type: Optional[str] = None
    scenario_slug: Optional[str] = None
    outcome: Optional[str] = None
    product_skus: list[str] = []
    impact: str = "OBSERVED"   # OBSERVED | INFERRED


class ScoreComponentItem(BaseModel):
    """One documented contribution to the impact score."""

    signal: str
    points: float
    note: str


class ImpactResponse(BaseModel):
    """The complete consequence/impact analysis for one transaction."""

    impact_id: str
    transaction_id: str
    scope: str                    # SINGLE_TRANSACTION | MULTI_TRANSACTION
    affected_transactions: int
    affected_orders: int
    affected_products: int
    observed_consequences: list[ConsequenceItem]
    derived_consequences: list[ConsequenceItem]
    potential_consequences: list[ConsequenceItem]
    severity: str
    impact_score: float
    shared_skus: list[str]
    shared_failure_patterns: list[str]
    affected: list[AffectedTransactionItem]
    score_components: list[ScoreComponentItem]
    event_ids: list[str]
    evidence_ids: list[str]
    metadata: dict = {}
