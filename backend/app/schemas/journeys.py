"""Read API contracts for journey reconstruction (Part 3).

The responses contain deterministic data only: events in chronological
order, the journey graph and structural integrity findings. No outcome
classification, no AI reasoning.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class JourneyEventItem(BaseModel):
    """One unified event as part of a reconstructed journey."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    payment_id: Optional[str] = None
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str
    idempotency_key: Optional[str] = None
    payload: dict
    # Position in the ingestion order (created_at, id) — NOT timestamp order.
    ingestion_position: int
    is_duplicate: bool = False
    is_unknown: bool = False
    is_orphan: bool = False
    duplicate_of_event_id: Optional[str] = None


class GraphNode(BaseModel):
    """One deterministic graph node."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str  # journey_root | correlation_root | event
    label: str
    event_type: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    payload_ref: Optional[str] = None
    position: dict


class GraphEdge(BaseModel):
    """One deterministic graph edge."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    target: str
    relationship_type: str
    rule_id: str
    reason: str


class JourneyGraphResponse(BaseModel):
    """The reconstructed journey as a serializable graph."""

    transaction_id: str
    correlation_id: Optional[str] = None
    layout: str = "deterministic_linear"
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class MissingCandidateItem(BaseModel):
    """A structurally expected event type that is absent (observation only)."""

    event_type: str
    rule_id: str
    note: str


class ContradictionItem(BaseModel):
    """Two mutually exclusive states both recorded (recorded, not resolved)."""

    type: str
    rule_id: str
    involved_event_ids: list[str]
    timestamps: list[datetime]
    explanation: str


class DuplicateItem(BaseModel):
    """An event identified as a duplicate of an earlier canonical event."""

    event_id: str
    event_type: str
    idempotency_key: str
    canonical_event_id: str
    rule_id: str


class OutOfOrderItem(BaseModel):
    """Timestamp order differs from ingestion order (nothing was mutated)."""

    event_id: str
    event_type: str
    timestamp: datetime
    ingestion_position: int
    chronological_position: int


class DelayedItem(BaseModel):
    """A webhook flagged as delayed (event or provider webhook row)."""

    event_id: str
    event_type: str
    delay_minutes: Optional[float] = None


class UnknownItem(BaseModel):
    """An event whose type/source is outside the centralized registry."""

    event_id: str
    event_type: str
    reason: str


class OrphanItem(BaseModel):
    """An event whose correlation does not match the journey's own."""

    event_id: str
    event_type: str
    correlation_id: str
    reason: str


class JourneyIntegrityResponse(BaseModel):
    """Structural integrity metadata for one reconstructed journey."""

    transaction_id: str
    total_events: int
    linked_events: int
    orphan_count: int
    duplicate_count: int
    unknown_count: int
    delayed_count: int
    out_of_order_count: int
    first_event_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    missing_expected_event_candidates: list[MissingCandidateItem]
    contradictions: list[ContradictionItem]
    duplicates: list[DuplicateItem]
    out_of_order_events: list[OutOfOrderItem]
    delayed_events: list[DelayedItem]
    unknown_events: list[UnknownItem]
    orphan_events: list[OrphanItem]


class JourneyResponse(BaseModel):
    """The complete reconstructed journey: events + graph + integrity."""

    transaction_id: str
    order_id: str
    payment_id: str
    correlation_id: Optional[str] = None
    events: list[JourneyEventItem]
    graph: JourneyGraphResponse
    integrity: JourneyIntegrityResponse