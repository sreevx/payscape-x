"""Evidence Engine domain models (Part 4).

Deterministic data structures produced by the evidence collector. Nothing in
this module decides the business outcome — it answers only:

    "What do we actually have evidence for?"

An evidence item always references the concrete records that support its
claim (event ids / domain record ids), carries a deterministic strength and
a confidence value derived purely from the evidence itself.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Evidence strength levels (deterministic semantics, documented in
# docs/architecture.md):
#   DIRECT        — the claiming event/record is present in the journey
#   CORROBORATED  — the claim is present AND an independent record agrees
#   INDIRECT      — inferred only from a related record (no direct event)
#   MISSING       — structurally expected but not observed (an evidence gap)
#   CONTRADICTED  — the claim's events exist but conflict with other events
STRENGTH_DIRECT = "DIRECT"
STRENGTH_CORROBORATED = "CORROBORATED"
STRENGTH_INDIRECT = "INDIRECT"
STRENGTH_MISSING = "MISSING"
STRENGTH_CONTRADICTED = "CONTRADICTED"

ALL_STRENGTHS = (
    STRENGTH_DIRECT,
    STRENGTH_CORROBORATED,
    STRENGTH_INDIRECT,
    STRENGTH_MISSING,
    STRENGTH_CONTRADICTED,
)

# Deterministic confidence values per strength level.
STRENGTH_CONFIDENCE: dict[str, float] = {
    STRENGTH_DIRECT: 1.0,
    STRENGTH_CORROBORATED: 1.0,
    STRENGTH_INDIRECT: 0.5,
    STRENGTH_MISSING: 0.0,
    STRENGTH_CONTRADICTED: 0.5,
}

# Evidence categories (spec §2).
CATEGORY_PAYMENT = "PAYMENT_EVIDENCE"
CATEGORY_ORDER = "ORDER_EVIDENCE"
CATEGORY_WEBHOOK = "WEBHOOK_EVIDENCE"
CATEGORY_INVENTORY = "INVENTORY_EVIDENCE"
CATEGORY_FULFILLMENT = "FULFILLMENT_EVIDENCE"
CATEGORY_SHIPMENT = "SHIPMENT_EVIDENCE"
CATEGORY_DELIVERY = "DELIVERY_EVIDENCE"
CATEGORY_REFUND = "REFUND_EVIDENCE"
CATEGORY_CUSTOMER_MESSAGE = "CUSTOMER_MESSAGE_EVIDENCE"
CATEGORY_TIMING = "TIMING_EVIDENCE"
CATEGORY_CORRELATION = "CORRELATION_EVIDENCE"


@dataclass
class EvidenceItem:
    """One deterministic evidence item about the journey."""

    evidence_id: str
    category: str
    claim: str
    event_ids: list[str]
    source: str
    timestamp: Optional[datetime]
    supporting_data: dict
    strength: str
    rule_id: str
    confidence: float
    contradictions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class EvidenceGap:
    """A structurally expected event type that was NOT observed."""

    event_type: str
    rule_id: str
    note: str


@dataclass
class EvidenceContradiction:
    """Two mutually exclusive states both recorded (preserved, not resolved)."""

    contradiction_id: str
    type: str
    rule_id: str
    event_ids: list[str]
    explanation: str
    severity: str  # LOW | MEDIUM | HIGH


@dataclass
class EvidenceReport:
    """The full evidence report for one transaction journey."""

    transaction_id: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    gaps: list[EvidenceGap] = field(default_factory=list)
    contradictions: list[EvidenceContradiction] = field(default_factory=list)

    @property
    def strength_summary(self) -> dict[str, int]:
        counts = {strength: 0 for strength in ALL_STRENGTHS}
        for item in self.evidence:
            counts[item.strength] += 1
        return counts


@dataclass
class WebhookView:
    """Webhook facts needed for evidence/corroboration (no ORM object)."""

    id: str
    event_type: str
    processing_status: str
    provider_payment_id: Optional[str] = None


@dataclass
class RefundView:
    """Refund facts needed for evidence/consistency checks."""

    id: str
    status: str
    amount: Optional[Decimal] = None


@dataclass
class DomainContext:
    """Deterministic view over the payment's domain records.

    Built once by the service layer from the existing Part 2 tables — the
    evidence and consistency engines never touch the database themselves.
    """

    payment_status: Optional[str] = None
    payment_amount: Optional[Decimal] = None
    payment_provider_payment_id: Optional[str] = None
    order_status: Optional[str] = None
    order_amount: Optional[Decimal] = None
    webhooks: list[WebhookView] = field(default_factory=list)
    refunds: list[RefundView] = field(default_factory=list)
    inventory_event_types: set[str] = field(default_factory=set)
    fulfillment_statuses: list[str] = field(default_factory=list)
    fulfillment_event_types: set[str] = field(default_factory=set)
    shipment_statuses: list[str] = field(default_factory=list)
    delivery_event_types: set[str] = field(default_factory=set)
    message_count: int = 0