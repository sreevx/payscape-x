"""Compound Failure Engine domain models (Part 6).

Deterministic structures produced by the compound-failure analysis. The
engine answers one question about a FAILED transaction:

    "What sequence of related failures caused this business outcome?"

It never predicts the future and never resolves contradictions. Every node,
edge and root cause is traceable to concrete event ids / evidence ids and
to the deterministic rule that produced it.

Three status labels are used consistently across Part 6:

- OBSERVED    — a record in the journey states the fact directly
- DERIVED     — the fact follows deterministically from observed records
                (never from probability or guesswork)
- POTENTIAL   — a possible future state signalled by records (complaint /
                contact), explicitly NOT an observed fact
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

STATUS_OBSERVED = "OBSERVED"
STATUS_DERIVED = "DERIVED"
STATUS_POTENTIAL = "POTENTIAL"

ALL_STATUSES = (STATUS_OBSERVED, STATUS_DERIVED, STATUS_POTENTIAL)

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"

# Edge relationship vocabulary (deterministic, never LLM-invented).
REL_CAUSES = "CAUSES"
REL_BLOCKS = "BLOCKS"
REL_LEADS_TO = "LEADS_TO"
REL_PREVENTS = "PREVENTS"
REL_IMPACTS = "IMPACTS"

# Failure classification of the compound result itself: OBSERVED when every
# chain node is an observed record, DERIVED when the chain relies on a
# derived step.
CLASS_OBSERVED = "OBSERVED"
CLASS_DERIVED = "DERIVED"

# When a compound failure is NOT detected, `reason` carries one of these
# deterministic codes so callers can explain the absence.
NOT_DETECTED_OUTCOME_FULFILLED = "NO_FAILURE_OUTCOME_FULFILLED"
NOT_DETECTED_OUTCOME_AT_RISK = "NO_DEFINITIVE_FAILURE_AT_RISK"
NOT_DETECTED_OUTCOME_UNVERIFIABLE = "OUTCOME_UNVERIFIABLE_NO_CHAIN"
NOT_DETECTED_SINGLE_STAGE = "SINGLE_STAGE_BUSINESS_FAILURE"
NOT_DETECTED_NO_FAILURE_RECORDS = "NO_FAILURE_RECORDS"


@dataclass
class FailureNode:
    """One node of the failure chain: a problem in one domain stage."""

    node_id: str
    kind: str                # e.g. INVENTORY_ALLOCATION_FAILED
    stage: str               # PAYMENT | WEBHOOK | ORDER | INVENTORY | FULFILLMENT |
                             # SHIPMENT | DELIVERY | CUSTOMER | REFUND
    label: str
    status: str              # OBSERVED | DERIVED
    message: str
    rule_id: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ChainEdge:
    """One deterministic edge between two failure-chain nodes."""

    edge_id: str
    source_node: str         # node_id
    target_node: str         # node_id
    relationship_type: str   # CAUSES | BLOCKS | LEADS_TO | PREVENTS | IMPACTS
    rule_id: str
    reason: str


@dataclass
class RootCause:
    """A deterministic root cause of the compound failure."""

    root_cause_id: str
    kind: str
    label: str
    stage: str
    explanation: str
    rule_id: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class CompoundFailureResult:
    """The complete compound-failure analysis for one transaction."""

    compound_failure_id: str
    transaction_id: str
    detected: bool
    reason: str               # classification note or NOT_DETECTED_* code
    severity: str             # LOW | MEDIUM | HIGH | CRITICAL
    classification: str       # OBSERVED | DERIVED (how the chain is evidenced)
    primary_failure: Optional[FailureNode] = None
    failure_chain: list[FailureNode] = field(default_factory=list)
    edges: list[ChainEdge] = field(default_factory=list)
    root_causes: list[RootCause] = field(default_factory=list)
    confidence: Optional[float] = None
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
