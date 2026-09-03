"""Evidence collection (Part 4).

Turns a reconstructed journey + the payment's domain records into a
structured, deterministic evidence report.

Claim rules map an event type (or a set of related records) to a
human-readable claim. Every reported item traces back to the concrete
event ids / record ids that support it. Gaps are structural observations
("X present but Y absent"), never business verdicts. Contradictions from
the Part 3 integrity report are preserved and surfaced on the affected
evidence items — never resolved, never deleted.

No LLM, no external calls, no randomness: same input, same report.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from app.core.events import EventType
from app.evidence.models import (
    CATEGORY_CORRELATION,
    CATEGORY_CUSTOMER_MESSAGE,
    CATEGORY_DELIVERY,
    CATEGORY_FULFILLMENT,
    CATEGORY_INVENTORY,
    CATEGORY_ORDER,
    CATEGORY_PAYMENT,
    CATEGORY_REFUND,
    CATEGORY_SHIPMENT,
    CATEGORY_TIMING,
    CATEGORY_WEBHOOK,
    DomainContext,
    EvidenceContradiction,
    EvidenceGap,
    EvidenceItem,
    EvidenceReport,
)
from app.evidence.strength import confidence_for, resolve_strength
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney

# ---------------------------------------------------------------------------
# Evidence gap rules — structural "X present but Y absent" observations.
# Mirrors the Part 3 missing-candidate idea, extended with the claims the
# evidence engine must be able to report as gaps (spec §6).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceGapRule:
    rule_id: str
    requires: frozenset[str]
    expects: frozenset[str]


EVIDENCE_GAP_RULES: list[EvidenceGapRule] = [
    EvidenceGapRule(
        "GAP_WEBHOOK_AFTER_CAPTURE",
        frozenset({EventType.PAYMENT_CAPTURED.value}),
        frozenset({EventType.WEBHOOK_RECEIVED.value}),
    ),
    EvidenceGapRule(
        "GAP_CONFIRMATION_AFTER_CAPTURE",
        frozenset({EventType.PAYMENT_CAPTURED.value}),
        frozenset({EventType.ORDER_CONFIRMED.value}),
    ),
    EvidenceGapRule(
        "GAP_ALLOCATION_AFTER_CONFIRMATION",
        frozenset({EventType.ORDER_CONFIRMED.value}),
        frozenset(
            {
                EventType.INVENTORY_RESERVED.value,
                EventType.INVENTORY_OUT_OF_STOCK.value,
            }
        ),
    ),
    EvidenceGapRule(
        "GAP_FULFILLMENT_AFTER_CONFIRMATION",
        frozenset({EventType.ORDER_CONFIRMED.value}),
        frozenset({EventType.FULFILLMENT_CREATED.value}),
    ),
    EvidenceGapRule(
        "GAP_SHIPMENT_AFTER_FULFILLMENT",
        frozenset({EventType.FULFILLMENT_SHIPPED.value}),
        frozenset({EventType.SHIPMENT_CREATED.value}),
    ),
    EvidenceGapRule(
        "GAP_DELIVERY_RESOLUTION",
        frozenset({EventType.SHIPMENT_CREATED.value}),
        frozenset(
            {
                EventType.SHIPMENT_IN_TRANSIT.value,
                EventType.DELIVERY_COMPLETED.value,
                EventType.DELIVERY_FAILED.value,
                EventType.DELIVERY_RETURNED.value,
            }
        ),
    ),
]


# ---------------------------------------------------------------------------
# Corroborators — independent records that agree with a claim's events.
# Each returns a supporting-data dict when corroboration exists, else None.
# ---------------------------------------------------------------------------

def _payments_corrob(ctx: DomainContext) -> Optional[dict]:
    if ctx.payment_status is not None:
        return {"payment_status": ctx.payment_status, "record": "payments"}
    return None


def _corrob_payment_captured(ctx: DomainContext) -> Optional[dict]:
    if ctx.payment_status == "CAPTURED":
        return {"payment_status": ctx.payment_status, "record": "payments"}
    hooks = [hook for hook in ctx.webhooks if hook.event_type == "payment.captured"]
    if hooks:
        return {
            "webhook_event": "payment.captured",
            "webhook_ids": [hook.id for hook in hooks],
            "record": "webhooks",
        }
    return None


def _corrob_payment_failed(ctx: DomainContext) -> Optional[dict]:
    if ctx.payment_status == "FAILED":
        return {"payment_status": ctx.payment_status, "record": "payments"}
    hooks = [hook for hook in ctx.webhooks if hook.event_type == "payment.failed"]
    if hooks:
        return {
            "webhook_event": "payment.failed",
            "webhook_ids": [hook.id for hook in hooks],
            "record": "webhooks",
        }
    return None


def _corrob_payment_refunded(ctx: DomainContext) -> Optional[dict]:
    if ctx.payment_status in ("REFUNDED", "PARTIALLY_REFUNDED"):
        return {"payment_status": ctx.payment_status, "record": "payments"}
    return None


def _corrob_order_confirmed(ctx: DomainContext) -> Optional[dict]:
    if ctx.order_status in ("CONFIRMED", "FULFILLING", "SHIPPED", "DELIVERED"):
        return {"order_status": ctx.order_status, "record": "orders"}
    return None


def _corrob_webhook_received(ctx: DomainContext) -> Optional[dict]:
    if ctx.webhooks:
        return {
            "webhook_count": len(ctx.webhooks),
            "record": "webhooks",
        }
    return None


def _corrob_webhook_delayed(ctx: DomainContext) -> Optional[dict]:
    delayed = [
        hook for hook in ctx.webhooks if hook.processing_status == "DELAYED"
    ]
    if delayed:
        return {
            "webhook_ids": [hook.id for hook in delayed],
            "processing_status": "DELAYED",
            "record": "webhooks",
        }
    return None


def _corrob_inventory_reserved(ctx: DomainContext) -> Optional[dict]:
    if "STOCK_RESERVED" in ctx.inventory_event_types:
        return {"inventory_event": "STOCK_RESERVED", "record": "inventory_events"}
    return None


def _corrob_inventory_out_of_stock(ctx: DomainContext) -> Optional[dict]:
    if "OUT_OF_STOCK" in ctx.inventory_event_types:
        return {"inventory_event": "OUT_OF_STOCK", "record": "inventory_events"}
    return None


def _corrob_fulfillment_created(ctx: DomainContext) -> Optional[dict]:
    if ctx.fulfillment_statuses:
        return {
            "fulfillment_status": ctx.fulfillment_statuses[-1],
            "record": "fulfillments",
        }
    return None


def _corrob_fulfillment_shipped(ctx: DomainContext) -> Optional[dict]:
    if "SHIPPED" in ctx.fulfillment_statuses:
        return {"fulfillment_status": "SHIPPED", "record": "fulfillments"}
    if "FULFILLMENT_SHIPPED" in ctx.fulfillment_event_types:
        return {"fulfillment_event": "FULFILLMENT_SHIPPED", "record": "fulfillment_events"}
    return None


def _corrob_shipment_created(ctx: DomainContext) -> Optional[dict]:
    if ctx.shipment_statuses:
        return {
            "shipment_status": ctx.shipment_statuses[-1],
            "record": "shipments",
        }
    return None


def _corrob_shipment_in_transit(ctx: DomainContext) -> Optional[dict]:
    if "IN_TRANSIT" in ctx.shipment_statuses:
        return {"shipment_status": "IN_TRANSIT", "record": "shipments"}
    if "IN_TRANSIT" in ctx.delivery_event_types or "PICKED_UP" in ctx.delivery_event_types:
        return {"delivery_event": "IN_TRANSIT", "record": "delivery_events"}
    return None


def _corrob_delivery_completed(ctx: DomainContext) -> Optional[dict]:
    if "DELIVERED" in ctx.shipment_statuses:
        return {"shipment_status": "DELIVERED", "record": "shipments"}
    if "DELIVERED" in ctx.delivery_event_types:
        return {"delivery_event": "DELIVERED", "record": "delivery_events"}
    return None


def _corrob_delivery_failed(ctx: DomainContext) -> Optional[dict]:
    if "FAILED" in ctx.shipment_statuses:
        return {"shipment_status": "FAILED", "record": "shipments"}
    if "DELIVERY_FAILED" in ctx.delivery_event_types:
        return {"delivery_event": "DELIVERY_FAILED", "record": "delivery_events"}
    return None


def _corrob_delivery_returned(ctx: DomainContext) -> Optional[dict]:
    if "RETURNED" in ctx.shipment_statuses:
        return {"shipment_status": "RETURNED", "record": "shipments"}
    if "RETURNED" in ctx.delivery_event_types or "RETURN_INITIATED" in ctx.delivery_event_types:
        return {"delivery_event": "RETURNED", "record": "delivery_events"}
    return None


def _corrob_customer_message(ctx: DomainContext) -> Optional[dict]:
    if ctx.message_count:
        return {"message_count": ctx.message_count, "record": "customer_messages"}
    return None


def _corrob_customer_complaint(ctx: DomainContext) -> Optional[dict]:
    if ctx.message_count:
        return {"message_count": ctx.message_count, "record": "customer_messages"}
    return None


def _corrob_refund_initiated(ctx: DomainContext) -> Optional[dict]:
    if ctx.refunds:
        return {
            "refund_ids": [refund.id for refund in ctx.refunds],
            "record": "refunds",
        }
    return None


def _corrob_refund_completed(ctx: DomainContext) -> Optional[dict]:
    completed = [refund for refund in ctx.refunds if refund.status == "COMPLETED"]
    if completed:
        return {
            "refund_ids": [refund.id for refund in completed],
            "status": "COMPLETED",
            "record": "refunds",
        }
    return None


# ---------------------------------------------------------------------------
# Claim registry — one entry per deterministic claim the engine can emit.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimRule:
    rule_id: str
    claim: str
    event_type: str
    category: str
    corroborator: Optional[Callable[[DomainContext], Optional[dict]]] = None
    source: str = "TRANSACTION_EVENT"


CLAIM_RULES: list[ClaimRule] = [
    ClaimRule(
        "PAYMENT_CREATED_PRESENT", "Payment was created",
        EventType.PAYMENT_CREATED.value, CATEGORY_PAYMENT, _payments_corrob,
    ),
    ClaimRule(
        "PAYMENT_CAPTURED_PRESENT", "Payment was captured",
        EventType.PAYMENT_CAPTURED.value, CATEGORY_PAYMENT, _corrob_payment_captured,
    ),
    ClaimRule(
        "PAYMENT_FAILED_PRESENT", "Payment failed",
        EventType.PAYMENT_FAILED.value, CATEGORY_PAYMENT, _corrob_payment_failed,
    ),
    ClaimRule(
        "PAYMENT_REFUNDED_PRESENT", "Payment was refunded",
        EventType.PAYMENT_REFUNDED.value, CATEGORY_PAYMENT, _corrob_payment_refunded,
    ),
    ClaimRule(
        "ORDER_CREATED_PRESENT", "Order was created",
        EventType.ORDER_CREATED.value, CATEGORY_ORDER, _payments_corrob,
    ),
    ClaimRule(
        "ORDER_CONFIRMED_PRESENT", "Order was confirmed",
        EventType.ORDER_CONFIRMED.value, CATEGORY_ORDER, _corrob_order_confirmed,
    ),
    ClaimRule(
        "WEBHOOK_RECEIVED_PRESENT", "Webhook was received",
        EventType.WEBHOOK_RECEIVED.value, CATEGORY_WEBHOOK, _corrob_webhook_received,
    ),
    ClaimRule(
        "WEBHOOK_DELAYED_PRESENT", "Webhook delivery was delayed",
        EventType.WEBHOOK_DELAYED.value, CATEGORY_WEBHOOK, _corrob_webhook_delayed,
    ),
    ClaimRule(
        "INVENTORY_RESERVED_PRESENT", "Inventory was reserved",
        EventType.INVENTORY_RESERVED.value, CATEGORY_INVENTORY, _corrob_inventory_reserved,
    ),
    ClaimRule(
        "INVENTORY_OUT_OF_STOCK_PRESENT", "Inventory was out of stock",
        EventType.INVENTORY_OUT_OF_STOCK.value, CATEGORY_INVENTORY,
        _corrob_inventory_out_of_stock,
    ),
    ClaimRule(
        "FULFILLMENT_CREATED_PRESENT", "Fulfillment was created",
        EventType.FULFILLMENT_CREATED.value, CATEGORY_FULFILLMENT,
        _corrob_fulfillment_created,
    ),
    ClaimRule(
        "FULFILLMENT_SHIPPED_PRESENT", "Fulfillment was shipped",
        EventType.FULFILLMENT_SHIPPED.value, CATEGORY_FULFILLMENT,
        _corrob_fulfillment_shipped,
    ),
    ClaimRule(
        "SHIPMENT_CREATED_PRESENT", "Shipment was created",
        EventType.SHIPMENT_CREATED.value, CATEGORY_SHIPMENT, _corrob_shipment_created,
    ),
    ClaimRule(
        "SHIPMENT_IN_TRANSIT_PRESENT", "Shipment is in transit",
        EventType.SHIPMENT_IN_TRANSIT.value, CATEGORY_SHIPMENT,
        _corrob_shipment_in_transit,
    ),
    ClaimRule(
        "DELIVERY_COMPLETED_PRESENT", "Delivery was completed",
        EventType.DELIVERY_COMPLETED.value, CATEGORY_DELIVERY,
        _corrob_delivery_completed,
    ),
    ClaimRule(
        "DELIVERY_FAILED_PRESENT", "Delivery failed",
        EventType.DELIVERY_FAILED.value, CATEGORY_DELIVERY, _corrob_delivery_failed,
    ),
    ClaimRule(
        "DELIVERY_RETURNED_PRESENT", "Delivery was returned",
        EventType.DELIVERY_RETURNED.value, CATEGORY_DELIVERY,
        _corrob_delivery_returned,
    ),
    ClaimRule(
        "CUSTOMER_MESSAGE_PRESENT", "Customer message was received",
        EventType.CUSTOMER_MESSAGE_RECEIVED.value, CATEGORY_CUSTOMER_MESSAGE,
        _corrob_customer_message,
    ),
    ClaimRule(
        "CUSTOMER_COMPLAINT_PRESENT", "Customer complaint was recorded",
        EventType.CUSTOMER_COMPLAINT.value, CATEGORY_CUSTOMER_MESSAGE,
        _corrob_customer_complaint,
    ),
    ClaimRule(
        "REFUND_INITIATED_PRESENT", "Refund was initiated",
        EventType.REFUND_INITIATED.value, CATEGORY_REFUND, _corrob_refund_initiated,
    ),
    ClaimRule(
        "REFUND_COMPLETED_PRESENT", "Refund was completed",
        EventType.REFUND_COMPLETED.value, CATEGORY_REFUND, _corrob_refund_completed,
    ),
]

CLAIM_BY_EVENT_TYPE: dict[str, ClaimRule] = {
    rule.event_type: rule for rule in CLAIM_RULES
}

# Contradiction severities (deterministic, by contradiction type).
CONTRADICTION_SEVERITY: dict[str, str] = {
    "PAYMENT_STATE_CONTRADICTION": "HIGH",
    "DELIVERY_STATE_CONTRADICTION": "MEDIUM",
    "REFUND_WITHOUT_INITIATION": "MEDIUM",
}


def _evidence_id(transaction_id: str, rule_id: str) -> str:
    """Deterministic evidence id: same transaction + rule -> same id."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"payscape:evidence:{transaction_id}:{rule_id}")
    )


def _contradiction_id(transaction_id: str, rule_id: str) -> str:
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"payscape:contradiction:{transaction_id}:{rule_id}")
    )


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def _detect_gaps(
    events: list[JourneyEvent], report: EvidenceReport
) -> dict[str, EvidenceGap]:
    """Fill report.gaps and return a map event_type -> gap."""
    present = {event.event_type for event in events}
    gap_by_type: dict[str, EvidenceGap] = {}
    for rule in EVIDENCE_GAP_RULES:
        if not rule.requires.issubset(present):
            continue
        if rule.expects & present:
            continue
        for expected in sorted(rule.expects):
            gap = EvidenceGap(
                event_type=expected,
                rule_id=rule.rule_id,
                note=(
                    f"{', '.join(sorted(rule.requires))} present but "
                    f"{expected} not observed"
                ),
            )
            report.gaps.append(gap)
            gap_by_type[expected] = gap
    return gap_by_type


def _contradictions_by_event(
    journey: ReconstructedJourney, integrity: JourneyIntegrity
) -> tuple[dict[str, list[str]], list[EvidenceContradiction]]:
    """Map event_id -> contradiction rule ids; also build the report's
    contradiction list. Preserved as-is from Part 3, never resolved."""
    by_event: dict[str, list[str]] = {}
    contradictions: list[EvidenceContradiction] = []
    for contradiction in integrity.contradictions:
        contradictions.append(
            EvidenceContradiction(
                contradiction_id=_contradiction_id(
                    journey.transaction_id, contradiction.rule_id
                ),
                type=contradiction.type,
                rule_id=contradiction.rule_id,
                event_ids=contradiction.involved_event_ids,
                explanation=contradiction.explanation,
                severity=CONTRADICTION_SEVERITY.get(contradiction.type, "MEDIUM"),
            )
        )
        for event_id in contradiction.involved_event_ids:
            by_event.setdefault(event_id, []).append(contradiction.rule_id)
    return by_event, contradictions


def _payload_summary(event: JourneyEvent) -> dict:
    """Compact deterministic view of an event's payload."""
    return {
        key: str(value)[:80]
        for key, value in (event.payload or {}).items()
    }


def _build_item(
    journey: ReconstructedJourney,
    rule: ClaimRule,
    events: list[JourneyEvent],
    corroboration: Optional[dict],
    contradiction_rule_ids: list[str],
    gap: Optional[EvidenceGap],
) -> Optional[EvidenceItem]:
    """Assemble one evidence item; None when the claim should not be emitted."""
    present = bool(events)
    strength = resolve_strength(
        present=present,
        corroborated=bool(corroboration),
        contradicted=bool(contradiction_rule_ids),
        structurally_expected=gap is not None,
    )
    if strength is None:
        return None

    if present:
        ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))
        timestamp = ordered[-1].timestamp
        event_ids = [event.event_id for event in ordered]
        supporting_data = {
            "events": [
                {
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                    "payload": _payload_summary(event),
                }
                for event in ordered
            ]
        }
        if corroboration:
            supporting_data["corroboration"] = corroboration
    else:
        timestamp = None
        event_ids = []
        supporting_data = {"note": gap.note if gap else "not observed"}

    return EvidenceItem(
        evidence_id=_evidence_id(journey.transaction_id, rule.rule_id),
        category=rule.category,
        claim=rule.claim,
        event_ids=event_ids,
        source=rule.source,
        timestamp=timestamp,
        supporting_data=supporting_data,
        strength=strength,
        rule_id=rule.rule_id,
        confidence=confidence_for(strength),
        contradictions=contradiction_rule_ids,
    )


def _timing_evidence(
    journey: ReconstructedJourney, events: list[JourneyEvent], report: EvidenceReport
) -> None:
    """TIMING_EVIDENCE: the delay facts observed in the stream."""
    delayed_events = [
        event
        for event in events
        if event.event_type == EventType.WEBHOOK_DELAYED.value
    ]
    if not delayed_events:
        return
    ordered = sorted(delayed_events, key=lambda event: (event.timestamp, event.event_id))
    delay_minutes = ordered[-1].payload.get("delay_minutes")
    try:
        delay = float(delay_minutes) if delay_minutes is not None else None
    except (TypeError, ValueError):
        delay = None
    report.evidence.append(
        EvidenceItem(
            evidence_id=_evidence_id(journey.transaction_id, "WEBHOOK_TIMING"),
            category=CATEGORY_TIMING,
            claim="Webhook delivery arrived late relative to capture",
            event_ids=[event.event_id for event in ordered],
            source="TRANSACTION_EVENT",
            timestamp=ordered[-1].timestamp,
            supporting_data={
                "delay_minutes": delay,
                "events": [
                    {
                        "event_id": event.event_id,
                        "timestamp": event.timestamp.isoformat(),
                        "payload": _payload_summary(event),
                    }
                    for event in ordered
                ],
            },
            strength="DIRECT",
            rule_id="WEBHOOK_TIMING_DELAY",
            confidence=confidence_for("DIRECT"),
        )
    )


def _correlation_evidence(
    journey: ReconstructedJourney, events: list[JourneyEvent], report: EvidenceReport
) -> None:
    """CORRELATION_EVIDENCE: how the events relate to the journey correlation."""
    if journey.correlation_id is None:
        return
    matching = [
        event.event_id
        for event in events
        if event.correlation_id == journey.correlation_id
    ]
    other_correlations = sorted(
        {event.correlation_id for event in events if event.correlation_id != journey.correlation_id}
    )
    report.evidence.append(
        EvidenceItem(
            evidence_id=_evidence_id(journey.transaction_id, "CORRELATION"),
            category=CATEGORY_CORRELATION,
            claim=(
                f"{len(matching)} of {len(events)} unified events share the "
                f"journey correlation"
            ),
            event_ids=matching,
            source="TRANSACTION_EVENT",
            timestamp=journey.last_event_at,
            supporting_data={
                "correlation_id": journey.correlation_id,
                "matching_events": len(matching),
                "total_events": len(events),
                "other_correlations": other_correlations,
            },
            strength="DIRECT",
            rule_id="JOURNEY_CORRELATION",
            confidence=confidence_for("DIRECT"),
        )
    )


def collect(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    context: DomainContext,
) -> EvidenceReport:
    """Build the deterministic evidence report for one journey.

    `integrity` is the Part 3 structural report (already computed by the
    caller) — its contradictions and gaps feed the evidence output so both
    engines describe the same raw stream.
    """
    events = journey.chronological_events
    report = EvidenceReport(transaction_id=journey.transaction_id)

    gap_by_type = _detect_gaps(events, report)
    contradictions_by_event, contradictions = _contradictions_by_event(
        journey, integrity
    )
    report.contradictions = contradictions

    by_type: dict[str, list[JourneyEvent]] = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event)

    for rule in CLAIM_RULES:
        rule_events = by_type.get(rule.event_type, [])
        corroboration = (
            rule.corroborator(context) if rule.corroborator is not None else None
        )
        involved = [
            rule_id
            for event in rule_events
            for rule_id in contradictions_by_event.get(event.event_id, [])
        ]
        item = _build_item(
            journey,
            rule,
            rule_events,
            corroboration,
            sorted(set(involved)),
            gap_by_type.get(rule.event_type),
        )
        if item is not None:
            report.evidence.append(item)

    _timing_evidence(journey, events, report)
    _correlation_evidence(journey, events, report)
    return report