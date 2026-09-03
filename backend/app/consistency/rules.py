"""Consistency rule registry (Part 4).

Every rule is explicit and documented: rule_id, name, description, severity
and a deterministic evaluation function. Rules answer whether the observed
records agree with each other — they never classify the business outcome.

Critical semantics (spec §10):

- A missing event is NOT automatically a violation. Rules whose inputs are
  absent return NOT_APPLICABLE (rule does not apply) or
  INSUFFICIENT_EVIDENCE (rule plausibly applies, key records absent).
- Absence of evidence is never turned into evidence of failure.
- Contradictory records are flagged as VIOLATION but never deleted and
  never resolved — both records are preserved.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from app.consistency.models import (
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS,
    STATUS_VIOLATION,
    CheckOutcome,
)
from app.core.events import EventType
from app.evidence.models import DomainContext
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney

# ---------------------------------------------------------------------------
# Evaluation input
# ---------------------------------------------------------------------------

@dataclass
class EvaluatorInput:
    """Everything a rule may read: the journey, grouped events, domain facts."""

    journey: ReconstructedJourney
    context: DomainContext
    by_type: dict[str, list[JourneyEvent]]


@dataclass(frozen=True)
class ConsistencyRule:
    rule_id: str
    name: str
    description: str
    severity: str
    evaluate: Callable[[EvaluatorInput], CheckOutcome]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _events(data: EvaluatorInput, *event_types: str) -> list[JourneyEvent]:
    """All events of the given types, chronological order."""
    events: list[JourneyEvent] = []
    for event_type in event_types:
        events.extend(data.by_type.get(event_type, []))
    return sorted(events, key=lambda event: (event.timestamp, event.event_id))


def _first(data: EvaluatorInput, event_type: str) -> Optional[JourneyEvent]:
    events = data.by_type.get(event_type, [])
    if not events:
        return None
    return sorted(events, key=lambda event: (event.timestamp, event.event_id))[0]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _payment_capture_requires_payment_created(data: EvaluatorInput) -> CheckOutcome:
    captured = _first(data, EventType.PAYMENT_CAPTURED.value)
    if captured is None:
        return CheckOutcome(
            "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
            STATUS_NOT_APPLICABLE, [],
            "no PAYMENT_CAPTURED event recorded — rule does not apply",
        )
    created = _first(data, EventType.PAYMENT_CREATED.value)
    if created is not None:
        return CheckOutcome(
            "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
            STATUS_PASS, [created.event_id, captured.event_id],
            "payment capture is preceded by a payment creation record",
        )
    return CheckOutcome(
        "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
        STATUS_VIOLATION, [captured.event_id],
        "PAYMENT_CAPTURED is recorded but no PAYMENT_CREATED exists",
    )


def _payment_capture_amount_matches_order(data: EvaluatorInput) -> CheckOutcome:
    if _first(data, EventType.PAYMENT_CAPTURED.value) is None:
        return CheckOutcome(
            "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
            STATUS_NOT_APPLICABLE, [],
            "no PAYMENT_CAPTURED event recorded — rule does not apply",
        )
    payment_amount = data.context.payment_amount
    order_amount = data.context.order_amount
    if payment_amount is None or order_amount is None:
        return CheckOutcome(
            "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
            STATUS_INSUFFICIENT_EVIDENCE, [],
            "payment or order amount records are missing — cannot compare",
        )
    if payment_amount == order_amount:
        return CheckOutcome(
            "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
            STATUS_PASS, [],
            (
                f"captured amount {payment_amount} matches the order amount "
                f"{order_amount}"
            ),
        )
    return CheckOutcome(
        "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
        STATUS_VIOLATION, [],
        (
            f"captured amount {payment_amount} differs from the order amount "
            f"{order_amount}"
        ),
    )


def _payment_failed_should_not_be_captured(data: EvaluatorInput) -> CheckOutcome:
    captured = _first(data, EventType.PAYMENT_CAPTURED.value)
    failed = _first(data, EventType.PAYMENT_FAILED.value)
    if captured is None and failed is None:
        return CheckOutcome(
            "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED",
            STATUS_NOT_APPLICABLE, [],
            "neither PAYMENT_CAPTURED nor PAYMENT_FAILED recorded — rule does not apply",
        )
    if captured is not None and failed is not None:
        # Both preserved; neither is deleted or preferred. The records
        # disagree, so the check is a violation.
        return CheckOutcome(
            "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED",
            STATUS_VIOLATION, [captured.event_id, failed.event_id],
            (
                "both PAYMENT_CAPTURED and PAYMENT_FAILED are recorded for the "
                "same payment; both preserved, flagged as contradictory"
            ),
        )
    return CheckOutcome(
        "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED",
        STATUS_PASS, [captured.event_id if captured else failed.event_id],
        (
            "payment state records agree: exactly one of captured/failed "
            "is recorded"
        ),
    )


def _webhook_payment_reference_valid(data: EvaluatorInput) -> CheckOutcome:
    webhooks = data.context.webhooks
    if not webhooks:
        return CheckOutcome(
            "WEBHOOK_PAYMENT_REFERENCE_VALID",
            STATUS_INSUFFICIENT_EVIDENCE, [],
            "no webhook records observed — nothing to validate",
        )
    expected = data.context.payment_provider_payment_id
    if not expected:
        return CheckOutcome(
            "WEBHOOK_PAYMENT_REFERENCE_VALID",
            STATUS_INSUFFICIENT_EVIDENCE, [],
            "payment provider reference is missing — cannot validate webhooks",
        )
    checked = [hook for hook in webhooks if hook.provider_payment_id]
    if not checked:
        return CheckOutcome(
            "WEBHOOK_PAYMENT_REFERENCE_VALID",
            STATUS_INSUFFICIENT_EVIDENCE, [],
            "no webhook payload carried a provider payment reference to validate",
        )
    mismatched = [
        hook for hook in checked if hook.provider_payment_id != expected
    ]
    if mismatched:
        return CheckOutcome(
            "WEBHOOK_PAYMENT_REFERENCE_VALID",
            STATUS_VIOLATION, [hook.id for hook in mismatched],
            (
                f"{len(mismatched)} webhook payload(s) reference a payment "
                f"other than {expected}"
            ),
        )
    return CheckOutcome(
        "WEBHOOK_PAYMENT_REFERENCE_VALID",
        STATUS_PASS, [hook.id for hook in checked],
        f"all {len(checked)} webhook payload references match the payment",
    )


def _order_confirmation_requires_order(data: EvaluatorInput) -> CheckOutcome:
    confirmed = _first(data, EventType.ORDER_CONFIRMED.value)
    if confirmed is None:
        return CheckOutcome(
            "ORDER_CONFIRMATION_REQUIRES_ORDER",
            STATUS_NOT_APPLICABLE, [],
            "no ORDER_CONFIRMED event recorded — rule does not apply",
        )
    created = _first(data, EventType.ORDER_CREATED.value)
    if created is not None:
        return CheckOutcome(
            "ORDER_CONFIRMATION_REQUIRES_ORDER",
            STATUS_PASS, [created.event_id, confirmed.event_id],
            "order confirmation is backed by an order creation record",
        )
    return CheckOutcome(
        "ORDER_CONFIRMATION_REQUIRES_ORDER",
        STATUS_VIOLATION, [confirmed.event_id],
        "ORDER_CONFIRMED is recorded but no ORDER_CREATED exists",
    )


def _inventory_reservation_requires_order(data: EvaluatorInput) -> CheckOutcome:
    reserved = _first(data, EventType.INVENTORY_RESERVED.value)
    if reserved is None:
        return CheckOutcome(
            "INVENTORY_RESERVATION_REQUIRES_ORDER",
            STATUS_NOT_APPLICABLE, [],
            "no INVENTORY_RESERVED event recorded — rule does not apply",
        )
    created = _first(data, EventType.ORDER_CREATED.value)
    if created is not None:
        return CheckOutcome(
            "INVENTORY_RESERVATION_REQUIRES_ORDER",
            STATUS_PASS, [created.event_id, reserved.event_id],
            "inventory reservation is backed by an order creation record",
        )
    return CheckOutcome(
        "INVENTORY_RESERVATION_REQUIRES_ORDER",
        STATUS_VIOLATION, [reserved.event_id],
        "INVENTORY_RESERVED is recorded but no ORDER_CREATED exists",
    )


def _inventory_reservation_quantity_positive(data: EvaluatorInput) -> CheckOutcome:
    reserved = _events(data, EventType.INVENTORY_RESERVED.value)
    if not reserved:
        return CheckOutcome(
            "INVENTORY_RESERVATION_QUANTITY_POSITIVE",
            STATUS_NOT_APPLICABLE, [],
            "no INVENTORY_RESERVED event recorded — rule does not apply",
        )
    non_positive = [
        event for event in reserved
        if _payload_quantity(event) is None or _payload_quantity(event) <= 0
    ]
    if non_positive:
        return CheckOutcome(
            "INVENTORY_RESERVATION_QUANTITY_POSITIVE",
            STATUS_VIOLATION, [event.event_id for event in non_positive],
            "inventory reservation(s) carry a non-positive or missing quantity",
        )
    return CheckOutcome(
        "INVENTORY_RESERVATION_QUANTITY_POSITIVE",
        STATUS_PASS, [event.event_id for event in reserved],
        "all inventory reservations carry a positive quantity",
    )


def _payload_quantity(event: JourneyEvent) -> Optional[int]:
    raw = (event.payload or {}).get("quantity")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _fulfillment_requires_order(data: EvaluatorInput) -> CheckOutcome:
    created = _first(data, EventType.FULFILLMENT_CREATED.value)
    if created is None:
        return CheckOutcome(
            "FULFILLMENT_REQUIRES_ORDER",
            STATUS_NOT_APPLICABLE, [],
            "no FULFILLMENT_CREATED event recorded — rule does not apply",
        )
    order = _first(data, EventType.ORDER_CREATED.value)
    if order is not None:
        return CheckOutcome(
            "FULFILLMENT_REQUIRES_ORDER",
            STATUS_PASS, [order.event_id, created.event_id],
            "fulfillment creation is backed by an order creation record",
        )
    return CheckOutcome(
        "FULFILLMENT_REQUIRES_ORDER",
        STATUS_VIOLATION, [created.event_id],
        "FULFILLMENT_CREATED is recorded but no ORDER_CREATED exists",
    )


def _shipment_requires_fulfillment(data: EvaluatorInput) -> CheckOutcome:
    shipment = _first(data, EventType.SHIPMENT_CREATED.value)
    if shipment is None:
        return CheckOutcome(
            "SHIPMENT_REQUIRES_FULFILLMENT",
            STATUS_NOT_APPLICABLE, [],
            "no SHIPMENT_CREATED event recorded — rule does not apply",
        )
    fulfillment = _first(data, EventType.FULFILLMENT_CREATED.value)
    if fulfillment is not None:
        return CheckOutcome(
            "SHIPMENT_REQUIRES_FULFILLMENT",
            STATUS_PASS, [fulfillment.event_id, shipment.event_id],
            "shipment creation is backed by a fulfillment creation record",
        )
    return CheckOutcome(
        "SHIPMENT_REQUIRES_FULFILLMENT",
        STATUS_VIOLATION, [shipment.event_id],
        "SHIPMENT_CREATED is recorded but no FULFILLMENT_CREATED exists",
    )


def _delivery_requires_shipment(data: EvaluatorInput) -> CheckOutcome:
    resolutions = _events(
        data,
        EventType.DELIVERY_COMPLETED.value,
        EventType.DELIVERY_FAILED.value,
        EventType.DELIVERY_RETURNED.value,
    )
    shipment = _first(data, EventType.SHIPMENT_CREATED.value)
    if not resolutions:
        if shipment is not None:
            return CheckOutcome(
                "DELIVERY_REQUIRES_SHIPMENT",
                STATUS_INSUFFICIENT_EVIDENCE, [shipment.event_id],
                (
                    "shipment is recorded but no delivery resolution event "
                    "(completed/failed/returned) was observed"
                ),
            )
        return CheckOutcome(
            "DELIVERY_REQUIRES_SHIPMENT",
            STATUS_NOT_APPLICABLE, [],
            "no shipment or delivery resolution events recorded — rule does not apply",
        )
    if shipment is not None:
        return CheckOutcome(
            "DELIVERY_REQUIRES_SHIPMENT",
            STATUS_PASS, [shipment.event_id] + [event.event_id for event in resolutions],
            "delivery resolution(s) are backed by a shipment creation record",
        )
    return CheckOutcome(
        "DELIVERY_REQUIRES_SHIPMENT",
        STATUS_VIOLATION, [event.event_id for event in resolutions],
        "delivery resolution(s) recorded without any SHIPMENT_CREATED",
    )


def _refund_requires_payment(data: EvaluatorInput) -> CheckOutcome:
    initiated = _first(data, EventType.REFUND_INITIATED.value)
    if initiated is None:
        return CheckOutcome(
            "REFUND_REQUIRES_PAYMENT",
            STATUS_NOT_APPLICABLE, [],
            "no REFUND_INITIATED event recorded — rule does not apply",
        )
    payment = _first(data, EventType.PAYMENT_CREATED.value)
    if payment is not None:
        return CheckOutcome(
            "REFUND_REQUIRES_PAYMENT",
            STATUS_PASS, [payment.event_id, initiated.event_id],
            "refund initiation is backed by a payment creation record",
        )
    return CheckOutcome(
        "REFUND_REQUIRES_PAYMENT",
        STATUS_VIOLATION, [initiated.event_id],
        "REFUND_INITIATED is recorded but no PAYMENT_CREATED exists",
    )


def _refund_amount_not_greater_than_captured(data: EvaluatorInput) -> CheckOutcome:
    if not data.context.refunds:
        return CheckOutcome(
            "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
            STATUS_NOT_APPLICABLE, [],
            "no refund records — rule does not apply",
        )
    captured_amount = data.context.payment_amount
    if captured_amount is None:
        return CheckOutcome(
            "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
            STATUS_INSUFFICIENT_EVIDENCE, [],
            "payment amount record is missing — cannot compare refund amounts",
        )
    exceeded = [
        refund for refund in data.context.refunds
        if refund.amount is not None and refund.amount > captured_amount
    ]
    if exceeded:
        return CheckOutcome(
            "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
            STATUS_VIOLATION, [refund.id for refund in exceeded],
            (
                f"refund amount(s) exceed the captured amount {captured_amount}"
            ),
        )
    return CheckOutcome(
        "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
        STATUS_PASS, [refund.id for refund in data.context.refunds],
        (
            f"all refund amounts are within the captured amount {captured_amount}"
        ),
    )


def _refund_completed_requires_refund_initiated(data: EvaluatorInput) -> CheckOutcome:
    completed = _first(data, EventType.REFUND_COMPLETED.value)
    if completed is None:
        return CheckOutcome(
            "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED",
            STATUS_NOT_APPLICABLE, [],
            "no REFUND_COMPLETED event recorded — rule does not apply",
        )
    initiated = _first(data, EventType.REFUND_INITIATED.value)
    if initiated is not None:
        return CheckOutcome(
            "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED",
            STATUS_PASS, [initiated.event_id, completed.event_id],
            "refund completion is backed by a refund initiation record",
        )
    return CheckOutcome(
        "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED",
        STATUS_VIOLATION, [completed.event_id],
        "REFUND_COMPLETED is recorded but no REFUND_INITIATED exists",
    )


def _delivered_after_shipment(data: EvaluatorInput) -> CheckOutcome:
    delivered = _first(data, EventType.DELIVERY_COMPLETED.value)
    shipment = _first(data, EventType.SHIPMENT_CREATED.value)
    if delivered is None:
        if shipment is not None:
            return CheckOutcome(
                "DELIVERED_AFTER_SHIPMENT",
                STATUS_INSUFFICIENT_EVIDENCE, [shipment.event_id],
                "delivery completion was not observed — ordering cannot be verified",
            )
        return CheckOutcome(
            "DELIVERED_AFTER_SHIPMENT",
            STATUS_NOT_APPLICABLE, [],
            "no delivery completion recorded — rule does not apply",
        )
    if shipment is None:
        return CheckOutcome(
            "DELIVERED_AFTER_SHIPMENT",
            STATUS_VIOLATION, [delivered.event_id],
            "delivery completion recorded without a shipment creation record",
        )
    if delivered.timestamp >= shipment.timestamp:
        return CheckOutcome(
            "DELIVERED_AFTER_SHIPMENT",
            STATUS_PASS, [shipment.event_id, delivered.event_id],
            "delivery completion is recorded after shipment creation",
        )
    return CheckOutcome(
        "DELIVERED_AFTER_SHIPMENT",
        STATUS_VIOLATION, [shipment.event_id, delivered.event_id],
        "delivery completion is recorded BEFORE shipment creation",
    )


def _fulfillment_shipped_after_created(data: EvaluatorInput) -> CheckOutcome:
    created = _first(data, EventType.FULFILLMENT_CREATED.value)
    shipped = _first(data, EventType.FULFILLMENT_SHIPPED.value)
    if created is None:
        return CheckOutcome(
            "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
            STATUS_NOT_APPLICABLE, [],
            "no FULFILLMENT_CREATED event recorded — rule does not apply",
        )
    if shipped is None:
        return CheckOutcome(
            "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
            STATUS_INSUFFICIENT_EVIDENCE, [created.event_id],
            "FULFILLMENT_SHIPPED was not observed — ordering cannot be verified",
        )
    if shipped.timestamp >= created.timestamp:
        return CheckOutcome(
            "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
            STATUS_PASS, [created.event_id, shipped.event_id],
            "fulfillment shipped is recorded after fulfillment creation",
        )
    return CheckOutcome(
        "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
        STATUS_VIOLATION, [created.event_id, shipped.event_id],
        "fulfillment shipped is recorded BEFORE fulfillment creation",
    )


def _order_confirmed_after_order_created(data: EvaluatorInput) -> CheckOutcome:
    confirmed = _first(data, EventType.ORDER_CONFIRMED.value)
    if confirmed is None:
        return CheckOutcome(
            "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
            STATUS_NOT_APPLICABLE, [],
            "no ORDER_CONFIRMED event recorded — rule does not apply",
        )
    created = _first(data, EventType.ORDER_CREATED.value)
    if created is None:
        return CheckOutcome(
            "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
            STATUS_INSUFFICIENT_EVIDENCE, [confirmed.event_id],
            "ORDER_CREATED was not observed — ordering cannot be verified",
        )
    if confirmed.timestamp >= created.timestamp:
        return CheckOutcome(
            "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
            STATUS_PASS, [created.event_id, confirmed.event_id],
            "order confirmation is recorded after order creation",
        )
    return CheckOutcome(
        "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
        STATUS_VIOLATION, [created.event_id, confirmed.event_id],
        "order confirmation is recorded BEFORE order creation",
    )


# ---------------------------------------------------------------------------
# The registry — evaluation order is fixed and deterministic.
# ---------------------------------------------------------------------------

CONSISTENCY_RULES: list[ConsistencyRule] = [
    ConsistencyRule(
        "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
        "Payment capture requires payment creation",
        "PAYMENT_CAPTURED must be backed by a PAYMENT_CREATED record.",
        SEVERITY_MEDIUM,
        _payment_capture_requires_payment_created,
    ),
    ConsistencyRule(
        "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
        "Captured amount matches order amount",
        "The captured payment amount must equal the order amount.",
        SEVERITY_HIGH,
        _payment_capture_amount_matches_order,
    ),
    ConsistencyRule(
        "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED",
        "Failed payment must not be captured",
        "PAYMENT_CAPTURED and PAYMENT_FAILED are mutually exclusive states; "
        "if both are recorded they are preserved and flagged as contradictory.",
        SEVERITY_HIGH,
        _payment_failed_should_not_be_captured,
    ),
    ConsistencyRule(
        "WEBHOOK_PAYMENT_REFERENCE_VALID",
        "Webhook payment reference is valid",
        "Every webhook payload that carries a provider payment id must "
        "reference the payment of this journey.",
        SEVERITY_MEDIUM,
        _webhook_payment_reference_valid,
    ),
    ConsistencyRule(
        "ORDER_CONFIRMATION_REQUIRES_ORDER",
        "Order confirmation requires an order",
        "ORDER_CONFIRMED must be backed by an ORDER_CREATED record.",
        SEVERITY_MEDIUM,
        _order_confirmation_requires_order,
    ),
    ConsistencyRule(
        "INVENTORY_RESERVATION_REQUIRES_ORDER",
        "Inventory reservation requires an order",
        "INVENTORY_RESERVED must be backed by an ORDER_CREATED record.",
        SEVERITY_MEDIUM,
        _inventory_reservation_requires_order,
    ),
    ConsistencyRule(
        "INVENTORY_RESERVATION_QUANTITY_POSITIVE",
        "Inventory reservation quantity is positive",
        "INVENTORY_RESERVED events must carry a positive quantity.",
        SEVERITY_MEDIUM,
        _inventory_reservation_quantity_positive,
    ),
    ConsistencyRule(
        "FULFILLMENT_REQUIRES_ORDER",
        "Fulfillment requires an order",
        "FULFILLMENT_CREATED must be backed by an ORDER_CREATED record.",
        SEVERITY_MEDIUM,
        _fulfillment_requires_order,
    ),
    ConsistencyRule(
        "SHIPMENT_REQUIRES_FULFILLMENT",
        "Shipment requires fulfillment",
        "SHIPMENT_CREATED must be backed by a FULFILLMENT_CREATED record.",
        SEVERITY_MEDIUM,
        _shipment_requires_fulfillment,
    ),
    ConsistencyRule(
        "DELIVERY_REQUIRES_SHIPMENT",
        "Delivery requires shipment",
        "Delivery resolution events (completed/failed/returned) must be "
        "backed by a SHIPMENT_CREATED record.",
        SEVERITY_MEDIUM,
        _delivery_requires_shipment,
    ),
    ConsistencyRule(
        "REFUND_REQUIRES_PAYMENT",
        "Refund requires a payment",
        "REFUND_INITIATED must be backed by a PAYMENT_CREATED record.",
        SEVERITY_MEDIUM,
        _refund_requires_payment,
    ),
    ConsistencyRule(
        "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
        "Refund amount within captured amount",
        "No refund amount may exceed the captured payment amount.",
        SEVERITY_HIGH,
        _refund_amount_not_greater_than_captured,
    ),
    ConsistencyRule(
        "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED",
        "Refund completion requires refund initiation",
        "REFUND_COMPLETED must be backed by a REFUND_INITIATED record.",
        SEVERITY_MEDIUM,
        _refund_completed_requires_refund_initiated,
    ),
    ConsistencyRule(
        "DELIVERED_AFTER_SHIPMENT",
        "Delivery completed after shipment",
        "DELIVERY_COMPLETED must be recorded no earlier than SHIPMENT_CREATED.",
        SEVERITY_MEDIUM,
        _delivered_after_shipment,
    ),
    ConsistencyRule(
        "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
        "Fulfillment shipped after fulfillment created",
        "FULFILLMENT_SHIPPED must be recorded no earlier than "
        "FULFILLMENT_CREATED.",
        SEVERITY_MEDIUM,
        _fulfillment_shipped_after_created,
    ),
    ConsistencyRule(
        "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
        "Order confirmed after order created",
        "ORDER_CONFIRMED must be recorded no earlier than ORDER_CREATED.",
        SEVERITY_MEDIUM,
        _order_confirmed_after_order_created,
    ),
]

RULE_BY_ID: dict[str, ConsistencyRule] = {
    rule.rule_id: rule for rule in CONSISTENCY_RULES
}