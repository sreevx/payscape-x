"""Consequence / Impact Engine domain models (Part 6).

Deterministic structures produced by the impact engine. The engine answers:

    "What are the downstream consequences of the detected failure?"

It strictly separates three labels (same vocabulary as the failure engine):

- OBSERVED    — stated by a record in the journey
- DERIVED     — follows deterministically from observed records
- POTENTIAL   — a possible future state signalled by records; never a fact

Cross-transaction impact is only reported when explicit shared identifiers
(the product SKU on OUT_OF_STOCK records) show the same condition hitting
other orders. Nothing is ever guessed or inferred semantically.
"""

from dataclasses import dataclass, field
from typing import Optional

# Consequence categories (spec § "CONSEQUENCE CATEGORIES").
CATEGORY_PAYMENT = "PAYMENT"
CATEGORY_ORDER = "ORDER"
CATEGORY_INVENTORY = "INVENTORY"
CATEGORY_FULFILLMENT = "FULFILLMENT"
CATEGORY_SHIPMENT = "SHIPMENT"
CATEGORY_DELIVERY = "DELIVERY"
CATEGORY_CUSTOMER = "CUSTOMER"
CATEGORY_REFUND = "REFUND"
CATEGORY_REVENUE = "REVENUE"
CATEGORY_OPERATIONAL = "OPERATIONAL"

ALL_CATEGORIES = (
    CATEGORY_PAYMENT,
    CATEGORY_ORDER,
    CATEGORY_INVENTORY,
    CATEGORY_FULFILLMENT,
    CATEGORY_SHIPMENT,
    CATEGORY_DELIVERY,
    CATEGORY_CUSTOMER,
    CATEGORY_REFUND,
    CATEGORY_REVENUE,
    CATEGORY_OPERATIONAL,
)

STATUS_OBSERVED = "OBSERVED"
STATUS_DERIVED = "DERIVED"
STATUS_POTENTIAL = "POTENTIAL"

SCOPE_SINGLE = "SINGLE_TRANSACTION"
SCOPE_MULTI = "MULTI_TRANSACTION"

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"

# How an affected cohort member is evidenced: OBSERVED when its own record
# stream shows the shared shortage, INFERRED when it only shares an
# identifier with the failing condition.
IMPACT_OBSERVED = "OBSERVED"
IMPACT_INFERRED = "INFERRED"


@dataclass
class ConsequenceItem:
    """One downstream consequence of the failure."""

    consequence_id: str
    category: str
    claim: str
    classification: str        # OBSERVED | DERIVED | POTENTIAL
    rule_id: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AffectedTransaction:
    """Another transaction hit by the same underlying condition."""

    transaction_id: str
    order_id: str
    external_order_id: str
    scenario_type: Optional[str]
    scenario_slug: Optional[str]
    outcome: Optional[str]
    product_skus: list[str] = field(default_factory=list)
    impact: str = IMPACT_OBSERVED   # OBSERVED | INFERRED


@dataclass
class CrossTransactionView:
    """Deterministic cross-transaction facts loaded by the service layer."""

    # SKUs this transaction failed to allocate.
    shortage_skus: list[str] = field(default_factory=list)
    # Other transactions that hit OUT_OF_STOCK on the same SKUs.
    others: list[AffectedTransaction] = field(default_factory=list)


@dataclass
class ScoreComponent:
    """One documented contribution to the deterministic impact score."""

    signal: str
    points: float
    note: str


@dataclass
class ImpactResult:
    """The complete consequence/impact analysis for one transaction."""

    impact_id: str
    transaction_id: str
    scope: str                       # SINGLE_TRANSACTION | MULTI_TRANSACTION
    affected_transactions: int
    affected_orders: int
    affected_products: int
    observed_consequences: list[ConsequenceItem] = field(default_factory=list)
    derived_consequences: list[ConsequenceItem] = field(default_factory=list)
    potential_consequences: list[ConsequenceItem] = field(default_factory=list)
    severity: str = SEVERITY_LOW
    impact_score: float = 0.0
    shared_skus: list[str] = field(default_factory=list)
    shared_failure_patterns: list[str] = field(default_factory=list)
    affected: list[AffectedTransaction] = field(default_factory=list)
    score_components: list[ScoreComponent] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
