"""Compound Failure rule registry (Part 6).

Two deterministic registries live here:

1. CHAIN_NODE_KINDS — the problem types the engine can place on a failure
   chain, each with the event types that evidence it (OBSERVED) or the
   structural condition that derives it (DERIVED), plus its severity.

2. CHAIN_RULES — how consecutive chain nodes relate (BLOCKS / LEADS_TO /
   CAUSES / PREVENTS / IMPACTS). The relationship is chosen from the two
   node kinds involved — never from an LLM, never from semantics.

The engine NEVER invents failures: a node is only created when its event
records exist in the journey (OBSERVED) or when a documented absence lets
it derive the node (DERIVED). Contradictory/missing evidence never forces a
chain — uncertainty keeps the compound failure undetected.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.events import EventType
from app.evidence.models import EvidenceReport
from app.failures.models import (
    CLASS_DERIVED,
    CLASS_OBSERVED,
    REL_BLOCKS,
    REL_CAUSES,
    REL_IMPACTS,
    REL_LEADS_TO,
    REL_PREVENTS,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    STATUS_DERIVED,
    STATUS_OBSERVED,
    FailureNode,
)
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import ReconstructedJourney

# Canonical domain stages in promise-chain order. Nodes are ordered along
# this axis first, then by earliest evidence timestamp, so the chain reads
# as a narrative (payment -> ... -> customer) instead of a raw sort.
STAGE_ORDER: list[str] = [
    "PAYMENT",
    "WEBHOOK",
    "ORDER",
    "INVENTORY",
    "FULFILLMENT",
    "SHIPMENT",
    "DELIVERY",
    "CUSTOMER",
    "REFUND",
]

STAGE_INDEX = {stage: index for index, stage in enumerate(STAGE_ORDER)}

# Severity of each stage when a problem is observed there.
STAGE_SEVERITY: dict[str, str] = {
    "PAYMENT": SEVERITY_HIGH,
    "WEBHOOK": SEVERITY_LOW,
    "ORDER": SEVERITY_MEDIUM,
    "INVENTORY": SEVERITY_HIGH,
    "FULFILLMENT": SEVERITY_HIGH,
    "SHIPMENT": SEVERITY_MEDIUM,
    "DELIVERY": SEVERITY_HIGH,
    "CUSTOMER": SEVERITY_MEDIUM,
    "REFUND": SEVERITY_MEDIUM,
}


@dataclass(frozen=True)
class NodeKind:
    """Definition of one failure-chain node kind."""

    kind: str
    stage: str
    label: str
    severity: str
    # Event types whose presence makes the node OBSERVED.
    observed_types: frozenset[str]
    # When no observed_types match, a DERIVED node is created if every type
    # in derived_requires is absent AND the outcome context applies.
    derived_requires: frozenset[str] = frozenset()
    message: str = ""


# ---------------------------------------------------------------------------
# Node messages (deterministic, factual phrasing)
# ---------------------------------------------------------------------------

def _inventory_message(present: set[str]) -> str:
    if EventType.INVENTORY_OUT_OF_STOCK.value in present:
        return (
            "Inventory allocation failed — the requested stock was not "
            "available (INVENTORY_OUT_OF_STOCK recorded)."
        )
    return "A stock reservation expired before the order was confirmed."


# ---------------------------------------------------------------------------
# Registry of node kinds
# ---------------------------------------------------------------------------
# Only failures that can terminate or block the promise chain belong on the
# chain. Order cancellations that merely follow a terminal payment failure
# are NOT independent nodes — they are consequences (handled by the impact
# engine), so a simple payment failure never masquerades as a compound one.

NODE_KIND_DEFS: list[NodeKind] = [
    NodeKind(
        kind="PAYMENT_FAILED",
        stage="PAYMENT",
        label="Payment failed — never captured",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.PAYMENT_FAILED.value}),
        message=(
            "Payment failed and was never captured; the business transaction "
            "could not proceed."
        ),
    ),
    NodeKind(
        kind="WEBHOOK_DELAYED",
        stage="WEBHOOK",
        label="Provider webhook delayed",
        severity=SEVERITY_LOW,
        observed_types=frozenset({EventType.WEBHOOK_DELAYED.value}),
        message="The provider webhook arrived late (delay flagged by the monitor).",
    ),
    NodeKind(
        kind="ORDER_NOT_CONFIRMED",
        stage="ORDER",
        label="Order never confirmed (SLA expired)",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.ORDER_NOT_CONFIRMED.value}),
        message=(
            "The order was never confirmed — the confirmation SLA window "
            "expired (ORDER_NOT_CONFIRMED recorded)."
        ),
    ),
    NodeKind(
        kind="ORDER_CANCELLED_AFTER_CAPTURE",
        stage="ORDER",
        label="Order cancelled after capture",
        severity=SEVERITY_MEDIUM,
        observed_types=frozenset({EventType.ORDER_CANCELLED.value}),
        message=(
            "The order was cancelled after the payment was captured; the "
            "goods were never delivered."
        ),
    ),
    NodeKind(
        kind="INVENTORY_RESERVATION_EXPIRED",
        stage="INVENTORY",
        label="Inventory reservation expired",
        severity=SEVERITY_MEDIUM,
        observed_types=frozenset({EventType.INVENTORY_RESERVATION_EXPIRED.value}),
        message=(
            "A stock reservation expired before fulfilment — the reserved "
            "units were released back to sellable stock."
        ),
    ),
    NodeKind(
        kind="INVENTORY_ALLOCATION_FAILED",
        stage="INVENTORY",
        label="Inventory allocation failed",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.INVENTORY_OUT_OF_STOCK.value}),
        message=_inventory_message({EventType.INVENTORY_OUT_OF_STOCK.value}),
    ),
    NodeKind(
        kind="FULFILLMENT_FAILED",
        stage="FULFILLMENT",
        label="Fulfillment failed",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.FULFILLMENT_FAILED.value}),
        message="Fulfillment failed — the goods were never packed or shipped.",
    ),
    NodeKind(
        kind="FULFILLMENT_NOT_CREATED",
        stage="FULFILLMENT",
        label="Fulfillment never created",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.NO_FULFILLMENT.value}),
        message=(
            "No fulfillment was ever created (NO_FULFILLMENT recorded) — "
            "the goods were never shipped."
        ),
    ),
    NodeKind(
        kind="SHIPMENT_NOT_CREATED",
        stage="SHIPMENT",
        label="Shipment never created",
        severity=SEVERITY_MEDIUM,
        # DERIVED: fulfillment exists (created/shipped) but no shipment row
        # or delivery activity ever appears.
        observed_types=frozenset(),
        derived_requires=frozenset({
            EventType.FULFILLMENT_CREATED.value,
            EventType.FULFILLMENT_SHIPPED.value,
            EventType.SHIPMENT_CREATED.value,
            EventType.SHIPMENT_IN_TRANSIT.value,
            EventType.DELIVERY_OUT_FOR_DELIVERY.value,
            EventType.DELIVERY_COMPLETED.value,
            EventType.DELIVERY_FAILED.value,
            EventType.DELIVERY_RETURNED.value,
        }),
        message=(
            "Fulfillment shipped but no shipment or delivery activity was "
            "recorded — the package never entered the delivery network."
        ),
    ),
    NodeKind(
        kind="DELIVERY_FAILED",
        stage="DELIVERY",
        label="Delivery failed",
        severity=SEVERITY_HIGH,
        observed_types=frozenset({EventType.DELIVERY_FAILED.value}),
        message="Delivery failed — the shipment never reached the customer.",
    ),
    NodeKind(
        kind="DELIVERY_RETURNED",
        stage="DELIVERY",
        label="Delivery returned to merchant",
        severity=SEVERITY_MEDIUM,
        observed_types=frozenset({EventType.DELIVERY_RETURNED.value}),
        message=(
            "The undelivered shipment was returned to the merchant "
            "(DELIVERY_RETURNED recorded)."
        ),
    ),
    NodeKind(
        kind="CUSTOMER_IMPACT",
        stage="CUSTOMER",
        label="Customer impact recorded",
        severity=SEVERITY_MEDIUM,
        # Complaints are always impact; messages count only when they are
        # about a problem (not a routine status enquiry / confirmation).
        observed_types=frozenset({
            EventType.CUSTOMER_COMPLAINT.value,
            EventType.CUSTOMER_MESSAGE_RECEIVED.value,
        }),
        message=(
            "The customer signalled a problem with the transaction "
            "(complaint or support message about the failure)."
        ),
    ),
]

NODE_KIND_BY_ID: dict[str, NodeKind] = {
    definition.kind: definition for definition in NODE_KIND_DEFS
}

# Message templates that only make sense when a customer actually
# complained (complaints raise the impact weight of the node).
IMPACT_ABOUTS = frozenset({
    "delivery_failure",
    "compound_failure",
    "inventory_failure",
    "no_fulfillment",
    "not_received",
})

# The impact engine / failure engine ignore messages that are routine
# enquiries or confirmations when deciding whether a CUSTOMER node exists.
NON_IMPACT_ABOUTS = frozenset({
    "status_enquiry",
    "refund_query",
    "confirmation",
    "cancel_request",
})


@dataclass(frozen=True)
class ChainRule:
    """How one pair of consecutive chain problems relates.

    `source_kinds` / `target_kinds` name the node kinds the rule connects.
    The engine walks the ordered chain and picks the first rule whose source
    kind matches the current node and whose target kind matches the next.
    """

    rule_id: str
    name: str
    relationship_type: str
    source_kinds: frozenset[str]
    target_kinds: frozenset[str]
    reason: str


CHAIN_RULES: list[ChainRule] = [
    ChainRule(
        "WEBHOOK_DELAY_LEADS_TO_ORDER_FAILURE",
        "Delayed webhook leads to order failure",
        REL_LEADS_TO,
        frozenset({"WEBHOOK_DELAYED"}),
        frozenset({"ORDER_NOT_CONFIRMED", "ORDER_CANCELLED_AFTER_CAPTURE"}),
        "The late provider webhook left the order unconfirmed until its SLA expired.",
    ),
    ChainRule(
        "ORDER_FAILURE_LEADS_TO_INVENTORY_FAILURE",
        "Order failure leads to inventory failure",
        REL_LEADS_TO,
        frozenset({"ORDER_NOT_CONFIRMED", "ORDER_CANCELLED_AFTER_CAPTURE"}),
        frozenset({"INVENTORY_RESERVATION_EXPIRED", "INVENTORY_ALLOCATION_FAILED"}),
        "An unconfirmed/cancelled order released or failed to secure its stock reservation.",
    ),
    ChainRule(
        "INVENTORY_EXPIRY_LEADS_TO_ALLOCATION_FAILURE",
        "Reservation expiry leads to allocation failure",
        REL_LEADS_TO,
        frozenset({"INVENTORY_RESERVATION_EXPIRED"}),
        frozenset({"INVENTORY_ALLOCATION_FAILED"}),
        "The expired reservation was followed by a failed re-allocation attempt.",
    ),
    ChainRule(
        "INVENTORY_FAILURE_BLOCKS_FULFILLMENT",
        "Inventory failure blocks fulfillment",
        REL_BLOCKS,
        frozenset({"INVENTORY_ALLOCATION_FAILED", "INVENTORY_RESERVATION_EXPIRED"}),
        frozenset({"FULFILLMENT_FAILED", "FULFILLMENT_NOT_CREATED"}),
        "Without allocated stock the fulfillment stage cannot proceed.",
    ),
    ChainRule(
        "FULFILLMENT_FAILURE_BLOCKS_SHIPMENT",
        "Fulfillment failure blocks shipment",
        REL_BLOCKS,
        frozenset({"FULFILLMENT_FAILED", "FULFILLMENT_NOT_CREATED"}),
        frozenset({"SHIPMENT_NOT_CREATED"}),
        "No fulfillment exists, so no shipment can be created.",
    ),
    ChainRule(
        "SHIPMENT_FAILURE_IMPACTS_DELIVERY",
        "Shipment failure impacts delivery",
        REL_PREVENTS,
        frozenset({"SHIPMENT_NOT_CREATED"}),
        frozenset({"DELIVERY_FAILED", "DELIVERY_RETURNED"}),
        "Without a shipment the delivery stage can never complete.",
    ),
    ChainRule(
        "DELIVERY_FAILURE_LEADS_TO_RETURN",
        "Delivery failure leads to return",
        REL_LEADS_TO,
        frozenset({"DELIVERY_FAILED"}),
        frozenset({"DELIVERY_RETURNED"}),
        "The failed delivery led to the shipment being returned to the merchant.",
    ),
    ChainRule(
        "DELIVERY_FAILURE_IMPACTS_CUSTOMER",
        "Delivery failure impacts customer",
        REL_IMPACTS,
        frozenset({"DELIVERY_FAILED", "DELIVERY_RETURNED"}),
        frozenset({"CUSTOMER_IMPACT"}),
        "A failed or returned delivery reached the customer as a problem.",
    ),
    ChainRule(
        "FULFILLMENT_FAILURE_IMPACTS_CUSTOMER",
        "Fulfillment failure impacts customer",
        REL_IMPACTS,
        frozenset({"FULFILLMENT_FAILED", "FULFILLMENT_NOT_CREATED"}),
        frozenset({"CUSTOMER_IMPACT"}),
        "The customer signalled the missing fulfillment as a problem.",
    ),
    ChainRule(
        "ORDER_FAILURE_IMPACTS_CUSTOMER",
        "Order failure impacts customer",
        REL_IMPACTS,
        frozenset({"ORDER_NOT_CONFIRMED", "ORDER_CANCELLED_AFTER_CAPTURE"}),
        frozenset({"CUSTOMER_IMPACT"}),
        "The customer signalled the failed/cancelled order as a problem.",
    ),
    ChainRule(
        "PAYMENT_FAILURE_CAUSES_ORDER_CANCELLATION",
        "Payment failure causes order cancellation",
        REL_CAUSES,
        frozenset({"PAYMENT_FAILED"}),
        frozenset({"ORDER_CANCELLED_AFTER_CAPTURE"}),
        "The terminal payment failure caused the order to be cancelled.",
    ),
    ChainRule(
        "WEBHOOK_DELAY_IMPACTS_CUSTOMER",
        "Webhook delay impacts customer",
        REL_IMPACTS,
        frozenset({"WEBHOOK_DELAYED"}),
        frozenset({"CUSTOMER_IMPACT"}),
        "The customer signalled the unresolved (delayed) transaction as a problem.",
    ),
]

# Consecutive-node default when no rule matches.
DEFAULT_RELATIONSHIP = REL_LEADS_TO
DEFAULT_RULE_ID = "CHAIN_PROGRESSION"
DEFAULT_REASON = "The failure progressed further along the business promise chain."
