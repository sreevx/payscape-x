"""Read API contract for the Compound Failure Engine (Part 6).

Responses are deterministic: nodes, edges and root causes trace back to the
exact event ids / evidence ids that support them and to the rule that
produced them. The engine reports OBSERVED / DERIVED / POTENTIAL labels —
it never presents potential consequences as facts and never predicts.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FailureNodeItem(BaseModel):
    """One node of the failure chain."""

    model_config = ConfigDict(from_attributes=True)

    node_id: str
    kind: str
    stage: str
    label: str
    status: str          # OBSERVED | DERIVED
    message: str
    rule_id: str
    event_ids: list[str]
    evidence_ids: list[str]
    timestamp: Optional[datetime] = None
    metadata: dict = {}


class ChainEdgeItem(BaseModel):
    """One deterministic edge between two failure-chain nodes."""

    model_config = ConfigDict(from_attributes=True)

    edge_id: str
    source_node: str
    target_node: str
    relationship_type: str   # CAUSES | BLOCKS | LEADS_TO | PREVENTS | IMPACTS
    rule_id: str
    reason: str


class RootCauseItem(BaseModel):
    """One deterministic root cause of the compound failure."""

    model_config = ConfigDict(from_attributes=True)

    root_cause_id: str
    kind: str
    label: str
    stage: str
    explanation: str
    rule_id: str
    event_ids: list[str]
    evidence_ids: list[str]


class CompoundFailureResponse(BaseModel):
    """The complete compound-failure analysis for one transaction."""

    compound_failure_id: str
    transaction_id: str
    detected: bool
    reason: str
    severity: str          # LOW | MEDIUM | HIGH | CRITICAL
    classification: str    # OBSERVED | DERIVED
    primary_failure: Optional[FailureNodeItem] = None
    failure_chain: list[FailureNodeItem]
    edges: list[ChainEdgeItem]
    root_causes: list[RootCauseItem]
    confidence: Optional[float] = None
    event_ids: list[str]
    evidence_ids: list[str]
    metadata: dict = {}


class FailureListItem(BaseModel):
    """One detected compound failure in the dataset list."""

    transaction_id: str
    order_id: str
    external_order_id: str
    scenario_type: Optional[str] = None
    scenario_slug: Optional[str] = None
    outcome: str
    severity: str
    classification: str
    detected: bool
    primary_failure_kind: Optional[str] = None
    primary_failure_label: Optional[str] = None
    root_cause_kinds: list[str]
    chain_length: int
    distinct_stages: list[str]
    confidence: Optional[float] = None
    scope: str = "SINGLE_TRANSACTION"
    affected_transactions: int = 1
    shared_skus: list[str] = []


class FailureListResponse(BaseModel):
    """Paginated dataset of detected compound failures."""

    items: list[FailureListItem]
    total: int
    limit: int
    offset: int
