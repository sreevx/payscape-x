"""Outcome rule registry (Part 5).

The decision hierarchy is an explicit, documented list. Rules run in fixed
priority order; the first rule whose preconditions match decides the
primary outcome. Rules that fire later with the SAME outcome add
corroborating reasons; rules with a different outcome are recorded in the
trace as overridden. Nothing is random and nothing is LLM-derived.

Documented hierarchy (see docs/architecture.md):

 1. CRITICAL_CONTRADICTION           -> UNVERIFIABLE  (no unjustified certainty)
 2. PAYMENT_FAILED_TERMINAL          -> FAILED        (business failure, not payment alone)
 3. PAYMENT_UNRESOLVED               -> UNVERIFIABLE  (payment state unknown)
 4. DELIVERY_FAILED_TERMINAL         -> FAILED        (definitive delivery failure)
 5. BUSINESS_FAILURE_MARKERS         -> FAILED        (SYSTEM markers: never confirmed / never fulfilled)
 6. INVENTORY_ALLOCATION_FAILED      -> FAILED        (definitive allocation failure)
 7. ORDER_CANCELLED_POST_CAPTURE     -> FAILED        (transaction reversed)
 8. TRANSACTION_FULFILLED            -> FULFILLED     (goods delivered)
 9. DELIVERY_PENDING_RISK            -> AT_RISK       (recoverable, unproven)
10. FULFILLMENT_PENDING_RISK         -> AT_RISK       (recoverable, unproven)
11. INSUFFICIENT_DOWNSTREAM_EVIDENCE -> UNVERIFIABLE  (records insufficient)
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.consistency.models import ConsistencyResult
from app.core.events import EventType
from app.evidence.models import EvidenceReport
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney
from app.outcome.models import (
    OUTCOME_AT_RISK,
    OUTCOME_FAILED,
    OUTCOME_FULFILLED,
    OUTCOME_UNVERIFIABLE,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    OutcomeReason,
)

# Contradiction types that touch critical lifecycle state. When one of
# these exists the engine refuses to produce certainty — UNLESS the
# delivery contradiction is temporally resolved (DELIVERY_COMPLETED strictly
# after every DELIVERY_FAILED), which the evaluator checks explicitly.
CRITICAL_CONTRADICTION_TYPES = (
    "PAYMENT_STATE_CONTRADICTION",
    "DELIVERY_STATE_CONTRADICTION",
)

# Lifecycle groups used for evidence completeness (only meaningful once the
# payment was captured). A group is "observed" when ANY of its event types
# appears — positive events and explicit-negative (SYSTEM) events both count.
COMPLETENESS_GROUPS: list[tuple[str, frozenset[str]]] = [
    ("confirmation", frozenset({EventType.ORDER_CONFIRMED.value,
                                EventType.ORDER_NOT_CONFIRMED.value,
                                EventType.ORDER_CANCELLED.value})),
    ("inventory", frozenset({EventType.INVENTORY_RESERVED.value,
                             EventType.INVENTORY_OUT_OF_STOCK.value,
                             EventType.INVENTORY_RESERVATION_EXPIRED.value})),
    ("fulfillment", frozenset({EventType.FULFILLMENT_CREATED.value,
                               EventType.NO_FULFILLMENT.value,
                               EventType.FULFILLMENT_FAILED.value})),
    ("shipment", frozenset({EventType.SHIPMENT_CREATED.value})),
    ("delivery", frozenset({EventType.DELIVERY_COMPLETED.value,
                            EventType.DELIVERY_FAILED.value,
                            EventType.DELIVERY_RETURNED.value})),
]


@dataclass
class EvaluationContext:
    """Everything a rule may read — all precomputed, all deterministic."""

    journey: ReconstructedJourney
    integrity: JourneyIntegrity
    evidence: EvidenceReport
    consistency: ConsistencyResult
    present_types: set = field(default_factory=set)
    events_by_type: dict = field(default_factory=dict)


@dataclass
class RuleMatch:
    """A successful rule evaluation: the outcome + its auditable reason."""

    reason: OutcomeReason


@dataclass(frozen=True)
class OutcomeRule:
    rule_id: str
    name: str
    description: str
    priority: int
    outcome: str
    severity: str
    # Event types this rule evaluates — used for documentation and for
    # tracing supporting evidence/events back to the matched records.
    evidence_types: frozenset[str]
    evaluate: Callable[[EvaluationContext], Optional[RuleMatch]]


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _events(ctx: EvaluationContext, *event_types: str) -> list[JourneyEvent]:
    events: list[JourneyEvent] = []
    for event_type in event_types:
        events.extend(ctx.events_by_type.get(event_type, []))
    return sorted(events, key=lambda event: (event.timestamp, event.event_id))


def _has_any(ctx: EvaluationContext, event_types: frozenset) -> bool:
    return any(event_type in ctx.present_types for event_type in event_types)


def _latest(ctx: EvaluationContext, event_type: str) -> Optional[JourneyEvent]:
    events = _events(ctx, event_type)
    return events[-1] if events else None


def _match_reason(
    rule: OutcomeRule,
    code: str,
    message: str,
    ctx: EvaluationContext,
    *event_types: str,
) -> RuleMatch:
    """Build a rule match whose reason traces to the rule's own event types."""
    involved = {
        event.event_id
        for event_types_chunk in event_types
        for event in _events(ctx, event_types_chunk)
    }
    reason = OutcomeReason(
        code=code,
        message=message,
        severity=rule.severity,
        rule_id=rule.rule_id,
        event_ids=sorted(involved),
    )
    return RuleMatch(reason=reason)


# ---------------------------------------------------------------------------
# Rule 1 — CRITICAL CONTRADICTION (UNVERIFIABLE)
# ---------------------------------------------------------------------------

def _delivery_contradiction_resolved(ctx: EvaluationContext) -> bool:
    """A delivery contradiction is resolved when DELIVERY_COMPLETED happened
    strictly AFTER every DELIVERY_FAILED — delivery ultimately succeeded."""
    completed = _events(ctx, EventType.DELIVERY_COMPLETED.value)
    failed = _events(ctx, EventType.DELIVERY_FAILED.value)
    if not completed or not failed:
        return False
    last_failure = failed[-1]
    return any(
        event.timestamp > last_failure.timestamp
        or (event.timestamp == last_failure.timestamp and event.event_id > last_failure.event_id)
        for event in completed
    )


def _critical_contradiction(ctx: EvaluationContext) -> Optional[RuleMatch]:
    unresolved = [
        contradiction
        for contradiction in ctx.evidence.contradictions
        if contradiction.type in CRITICAL_CONTRADICTION_TYPES
    ]
    if not unresolved:
        return None
    # A DELIVERY contradiction is resolvable by ordering: when the delivery
    # was completed strictly AFTER every failure, delivery ultimately
    # succeeded and the contradiction does not block classification. A
    # payment-state contradiction is never resolvable.
    if _delivery_contradiction_resolved(ctx):
        unresolved = [
            contradiction
            for contradiction in unresolved
            if contradiction.type != "DELIVERY_STATE_CONTRADICTION"
        ]
        if not unresolved:
            return None
    involved = sorted(
        {
            event_id
            for contradiction in unresolved
            for event_id in contradiction.event_ids
        }
    )
    message = (
        "Conflicting critical lifecycle records were found "
        f"({' · '.join(sorted({item.type for item in unresolved}))}) — "
        "both sides are preserved and neither is preferred, so a reliable "
        "business outcome cannot be classified."
    )
    rule = _RULE_CRITICAL_CONTRADICTION
    reason = OutcomeReason(
        code="CONTRADICTORY_RECORDS",
        message=message,
        severity=SEVERITY_HIGH,
        rule_id=rule.rule_id,
        event_ids=involved,
    )
    return RuleMatch(reason=reason)


_RULE_CRITICAL_CONTRADICTION = OutcomeRule(
    "CRITICAL_CONTRADICTION",
    "Critical lifecycle contradiction",
    "Mutually exclusive critical records (payment captured+failed, delivered+"
    "failed) block reliable classification unless delivery ordering resolves "
    "them. Contradictions are preserved, never resolved by deletion.",
    10,
    OUTCOME_UNVERIFIABLE,
    SEVERITY_HIGH,
    frozenset({EventType.PAYMENT_CAPTURED.value, EventType.PAYMENT_FAILED.value,
               EventType.DELIVERY_COMPLETED.value, EventType.DELIVERY_FAILED.value}),
    _critical_contradiction,
)


# ---------------------------------------------------------------------------
# Rule 2 — PAYMENT FAILED (FAILED)
# ---------------------------------------------------------------------------

def _payment_failed_terminal(ctx: EvaluationContext) -> Optional[RuleMatch]:
    failed = _events(ctx, EventType.PAYMENT_FAILED.value)
    if not failed or EventType.PAYMENT_CAPTURED.value in ctx.present_types:
        return None
    return _match_reason(
        _RULE_PAYMENT_FAILED,
        "PAYMENT_DECLINED",
        "Payment failed and was never captured; the order could not proceed "
        "and no goods were shipped.",
        ctx,
        EventType.PAYMENT_FAILED.value,
        EventType.ORDER_CANCELLED.value,
    )


_RULE_PAYMENT_FAILED = OutcomeRule(
    "PAYMENT_FAILED_TERMINAL",
    "Payment failed — business transaction did not proceed",
    "A payment failure with no later capture means the business transaction "
    "cannot complete. Distinguishes business failure from a later payment "
    "state: if a capture ever appears, the contradiction rule handles it.",
    20,
    OUTCOME_FAILED,
    SEVERITY_HIGH,
    frozenset({EventType.PAYMENT_FAILED.value, EventType.PAYMENT_CAPTURED.value,
               EventType.ORDER_CANCELLED.value}),
    _payment_failed_terminal,
)


# ---------------------------------------------------------------------------
# Rule 3 — PAYMENT UNRESOLVED (UNVERIFIABLE)
# ---------------------------------------------------------------------------

def _payment_unresolved(ctx: EvaluationContext) -> Optional[RuleMatch]:
    captured = EventType.PAYMENT_CAPTURED.value in ctx.present_types
    failed = EventType.PAYMENT_FAILED.value in ctx.present_types
    if captured or failed:
        return None
    return _match_reason(
        _RULE_PAYMENT_UNRESOLVED,
        "UNRESOLVED_PAYMENT_STATE",
        "Neither payment capture nor payment failure was recorded; the "
        "payment outcome is unknown.",
        ctx,
        EventType.PAYMENT_CREATED.value,
        EventType.PAYMENT_AUTHORIZED.value,
    )


_RULE_PAYMENT_UNRESOLVED = OutcomeRule(
    "PAYMENT_UNRESOLVED",
    "Payment outcome unresolved",
    "No capture and no failure event — the payment state cannot be "
    "established, so nothing downstream can be concluded.",
    30,
    OUTCOME_UNVERIFIABLE,
    SEVERITY_MEDIUM,
    frozenset({EventType.PAYMENT_CREATED.value, EventType.PAYMENT_AUTHORIZED.value,
               EventType.PAYMENT_CAPTURED.value, EventType.PAYMENT_FAILED.value}),
    _payment_unresolved,
)


# ---------------------------------------------------------------------------
# Rule 4 — DELIVERY FAILED (FAILED)
# ---------------------------------------------------------------------------

def _delivery_failed_terminal(ctx: EvaluationContext) -> Optional[RuleMatch]:
    if EventType.DELIVERY_FAILED.value not in ctx.present_types:
        return None
    if EventType.DELIVERY_COMPLETED.value in ctx.present_types:
        return None  # handled by contradiction / fulfillment rules
    returned = EventType.DELIVERY_RETURNED.value in ctx.present_types
    message = (
        "Shipment delivery failed and was never completed"
        + ("; the goods were returned to the merchant" if returned else "")
        + "; the customer did not receive the order."
    )
    return _match_reason(
        _RULE_DELIVERY_FAILED,
        "DELIVERY_FAILED",
        message,
        ctx,
        EventType.DELIVERY_FAILED.value,
        EventType.DELIVERY_RETURNED.value,
    )


_RULE_DELIVERY_FAILED = OutcomeRule(
    "DELIVERY_FAILED_TERMINAL",
    "Delivery definitively failed",
    "A delivery failure with no later delivery completion means the goods "
    "never reached the customer — the business promise cannot be met.",
    40,
    OUTCOME_FAILED,
    SEVERITY_HIGH,
    frozenset({EventType.DELIVERY_FAILED.value, EventType.DELIVERY_RETURNED.value,
               EventType.DELIVERY_COMPLETED.value}),
    _delivery_failed_terminal,
)


# ---------------------------------------------------------------------------
# Rule 5 — BUSINESS FAILURE MARKERS (FAILED)
# ---------------------------------------------------------------------------

_FAILURE_MARKER_REASONS: list[tuple[str, str]] = [
    (EventType.ORDER_NOT_CONFIRMED.value, (
        "ORDER_NOT_CONFIRMED",
        "Confirmation SLA expired — the order was never confirmed, so no "
        "fulfillment could follow.")),
    (EventType.NO_FULFILLMENT.value, (
        "NO_FULFILLMENT",
        "No fulfillment was ever created (NO_FULFILLMENT); the goods were "
        "never shipped.")),
    (EventType.FULFILLMENT_FAILED.value, (
        "FULFILLMENT_FAILED",
        "Fulfillment failed; the goods were never shipped.")),
]


def _business_failure_markers(ctx: EvaluationContext) -> Optional[RuleMatch]:
    for marker, (code, message) in _FAILURE_MARKER_REASONS:
        if marker not in ctx.present_types:
            continue
        # The reason traces every present marker (and any reservation
        # expiry) so compound chains surface the full failure record.
        return _match_reason(
            _RULE_BUSINESS_FAILURE_MARKERS,
            code,
            message,
            ctx,
            EventType.ORDER_NOT_CONFIRMED.value,
            EventType.NO_FULFILLMENT.value,
            EventType.FULFILLMENT_FAILED.value,
            EventType.INVENTORY_RESERVATION_EXPIRED.value,
        )
    return None


_RULE_BUSINESS_FAILURE_MARKERS = OutcomeRule(
    "BUSINESS_FAILURE_MARKERS",
    "Explicit business failure markers",
    "SYSTEM failure markers (ORDER_NOT_CONFIRMED, NO_FULFILLMENT, "
    "FULFILLMENT_FAILED) are explicit business-level records that the "
    "promised transaction did not complete.",
    50,
    OUTCOME_FAILED,
    SEVERITY_HIGH,
    frozenset({EventType.ORDER_NOT_CONFIRMED.value, EventType.NO_FULFILLMENT.value,
               EventType.FULFILLMENT_FAILED.value,
               EventType.INVENTORY_RESERVATION_EXPIRED.value}),
    _business_failure_markers,
)


# ---------------------------------------------------------------------------
# Rule 6 — INVENTORY ALLOCATION FAILED (FAILED)
# ---------------------------------------------------------------------------

def _inventory_allocation_failed(ctx: EvaluationContext) -> Optional[RuleMatch]:
    out_of_stock = _events(ctx, EventType.INVENTORY_OUT_OF_STOCK.value)
    if not out_of_stock:
        return None
    if EventType.DELIVERY_COMPLETED.value in ctx.present_types:
        return None
    first_out_of_stock = out_of_stock[0]
    later_reservations = [
        event
        for event in _events(ctx, EventType.INVENTORY_RESERVED.value)
        if event.timestamp > first_out_of_stock.timestamp
    ]
    if later_reservations:
        return None  # allocation may have recovered afterwards
    expired = EventType.INVENTORY_RESERVATION_EXPIRED.value in ctx.present_types
    message = (
        "Inventory allocation failed (INVENTORY_OUT_OF_STOCK) after payment"
        + (" and a prior reservation expired" if expired else "")
        + "; the order could not be fulfilled."
    )
    return _match_reason(
        _RULE_INVENTORY_ALLOCATION_FAILED,
        "INVENTORY_ALLOCATION_FAILED",
        message,
        ctx,
        EventType.INVENTORY_OUT_OF_STOCK.value,
        EventType.INVENTORY_RESERVATION_EXPIRED.value,
    )


_RULE_INVENTORY_ALLOCATION_FAILED = OutcomeRule(
    "INVENTORY_ALLOCATION_FAILED",
    "Inventory allocation failed",
    "OUT_OF_STOCK with no successful later reservation and no delivery means "
    "stock could never be allocated for the order.",
    60,
    OUTCOME_FAILED,
    SEVERITY_HIGH,
    frozenset({EventType.INVENTORY_OUT_OF_STOCK.value,
               EventType.INVENTORY_RESERVED.value,
               EventType.INVENTORY_RESERVATION_EXPIRED.value}),
    _inventory_allocation_failed,
)


# ---------------------------------------------------------------------------
# Rule 7 — ORDER CANCELLED AFTER PAYMENT (FAILED)
# ---------------------------------------------------------------------------

def _order_cancelled_post_capture(ctx: EvaluationContext) -> Optional[RuleMatch]:
    if EventType.ORDER_CANCELLED.value not in ctx.present_types:
        return None
    if EventType.PAYMENT_CAPTURED.value not in ctx.present_types:
        return None
    if EventType.DELIVERY_COMPLETED.value in ctx.present_types:
        return None
    refunded = any(
        event_type in ctx.present_types
        for event_type in (EventType.REFUND_COMPLETED.value,
                           EventType.PAYMENT_REFUNDED.value,
                           EventType.REFUND_INITIATED.value)
    )
    message = (
        "Order was cancelled after payment"
        + (" and the payment was refunded" if refunded else "")
        + "; the goods were never delivered and the transaction was reversed."
    )
    return _match_reason(
        _RULE_ORDER_CANCELLED,
        "ORDER_CANCELLED_AFTER_PAYMENT",
        message,
        ctx,
        EventType.ORDER_CANCELLED.value,
        EventType.REFUND_INITIATED.value,
        EventType.REFUND_COMPLETED.value,
        EventType.PAYMENT_REFUNDED.value,
    )


_RULE_ORDER_CANCELLED = OutcomeRule(
    "ORDER_CANCELLED_POST_CAPTURE",
    "Order cancelled after payment",
    "A captured order that is cancelled never delivers its promise. When a "
    "refund exists it is recorded as part of the reason — the outcome comes "
    "from the business state (cancelled, not delivered), not from the "
    "existence of a refund.",
    70,
    OUTCOME_FAILED,
    SEVERITY_HIGH,
    frozenset({EventType.ORDER_CANCELLED.value, EventType.PAYMENT_CAPTURED.value,
               EventType.REFUND_INITIATED.value, EventType.REFUND_COMPLETED.value,
               EventType.PAYMENT_REFUNDED.value, EventType.DELIVERY_COMPLETED.value}),
    _order_cancelled_post_capture,
)


# ---------------------------------------------------------------------------
# Rule 8 — TRANSACTION FULFILLED (FULFILLED)
# ---------------------------------------------------------------------------

def _transaction_fulfilled(ctx: EvaluationContext) -> Optional[RuleMatch]:
    if EventType.DELIVERY_COMPLETED.value not in ctx.present_types:
        return None
    return _match_reason(
        _RULE_TRANSACTION_FULFILLED,
        "DELIVERED_TO_CUSTOMER",
        "Delivery completed — the order reached the customer "
        "(DELIVERY_COMPLETED).",
        ctx,
        EventType.DELIVERY_COMPLETED.value,
    )


_RULE_TRANSACTION_FULFILLED = OutcomeRule(
    "TRANSACTION_FULFILLED",
    "Business transaction fulfilled",
    "DELIVERY_COMPLETED is the definitive positive terminal record of the "
    "promise chain. FULFILLED is only ever assigned on this evidence — never "
    "on payment success alone.",
    80,
    OUTCOME_FULFILLED,
    SEVERITY_LOW,
    frozenset({EventType.DELIVERY_COMPLETED.value}),
    _transaction_fulfilled,
)


# ---------------------------------------------------------------------------
# Rule 9 — DELIVERY PENDING (AT_RISK)
# ---------------------------------------------------------------------------

def _delivery_pending_risk(ctx: EvaluationContext) -> Optional[RuleMatch]:
    progressed = _has_any(
        ctx,
        frozenset({EventType.SHIPMENT_CREATED.value,
                   EventType.SHIPMENT_IN_TRANSIT.value,
                   EventType.DELIVERY_OUT_FOR_DELIVERY.value}),
    )
    resolved = _has_any(
        ctx,
        frozenset({EventType.DELIVERY_COMPLETED.value,
                   EventType.DELIVERY_FAILED.value,
                   EventType.DELIVERY_RETURNED.value}),
    )
    if not progressed or resolved:
        return None
    in_transit = EventType.SHIPMENT_IN_TRANSIT.value in ctx.present_types
    message = (
        "Shipment is " + ("in transit" if in_transit else "created")
        + " with no delivery resolution recorded; successful delivery "
        "remains possible but is not yet proven."
    )
    return _match_reason(
        _RULE_DELIVERY_PENDING,
        "DELIVERY_PENDING",
        message,
        ctx,
        EventType.SHIPMENT_CREATED.value,
        EventType.SHIPMENT_IN_TRANSIT.value,
        EventType.DELIVERY_OUT_FOR_DELIVERY.value,
    )


_RULE_DELIVERY_PENDING = OutcomeRule(
    "DELIVERY_PENDING_RISK",
    "Delivery pending — at risk",
    "The shipment exists but no delivery resolution has been recorded. "
    "Recoverable operational risk: completion is still possible.",
    90,
    OUTCOME_AT_RISK,
    SEVERITY_MEDIUM,
    frozenset({EventType.SHIPMENT_CREATED.value, EventType.SHIPMENT_IN_TRANSIT.value,
               EventType.DELIVERY_OUT_FOR_DELIVERY.value}),
    _delivery_pending_risk,
)


# ---------------------------------------------------------------------------
# Rule 10 — FULFILLMENT PENDING (AT_RISK)
# ---------------------------------------------------------------------------

def _fulfillment_pending_risk(ctx: EvaluationContext) -> Optional[RuleMatch]:
    if EventType.FULFILLMENT_CREATED.value not in ctx.present_types:
        return None
    if EventType.FULFILLMENT_SHIPPED.value in ctx.present_types:
        return None
    if EventType.SHIPMENT_CREATED.value in ctx.present_types:
        return None
    return _match_reason(
        _RULE_FULFILLMENT_PENDING,
        "FULFILLMENT_PENDING",
        "Fulfillment was created but has not shipped; completion remains "
        "possible but is not yet proven.",
        ctx,
        EventType.FULFILLMENT_CREATED.value,
    )


_RULE_FULFILLMENT_PENDING = OutcomeRule(
    "FULFILLMENT_PENDING_RISK",
    "Fulfillment pending — at risk",
    "The order was confirmed and fulfillment started, but nothing has "
    "shipped yet. Recoverable operational risk.",
    100,
    OUTCOME_AT_RISK,
    SEVERITY_MEDIUM,
    frozenset({EventType.FULFILLMENT_CREATED.value,
               EventType.FULFILLMENT_SHIPPED.value,
               EventType.SHIPMENT_CREATED.value}),
    _fulfillment_pending_risk,
)


# ---------------------------------------------------------------------------
# Rule 11 — INSUFFICIENT DOWNSTREAM EVIDENCE (UNVERIFIABLE)
# ---------------------------------------------------------------------------

def _insufficient_downstream(ctx: EvaluationContext) -> Optional[RuleMatch]:
    if EventType.PAYMENT_CAPTURED.value not in ctx.present_types:
        return None
    return _match_reason(
        _RULE_INSUFFICIENT_DOWNSTREAM,
        "INSUFFICIENT_LIFECYCLE_EVIDENCE",
        "Payment was captured but the downstream business lifecycle "
        "(confirmation, inventory, fulfillment, shipment, delivery) was not "
        "observed; the actual business outcome cannot be established.",
        ctx,
        EventType.PAYMENT_CAPTURED.value,
    )


_RULE_INSUFFICIENT_DOWNSTREAM = OutcomeRule(
    "INSUFFICIENT_DOWNSTREAM_EVIDENCE",
    "Insufficient downstream lifecycle evidence",
    "Capture exists but none of the downstream lifecycle records do, and no "
    "explicit failure marker exists. Absence of evidence is NOT treated as "
    "business failure — the outcome is unverifiable.",
    110,
    OUTCOME_UNVERIFIABLE,
    SEVERITY_MEDIUM,
    frozenset({EventType.PAYMENT_CAPTURED.value}),
    _insufficient_downstream,
)


# ---------------------------------------------------------------------------
# The registry — evaluation order is fixed by priority.
# ---------------------------------------------------------------------------

OUTCOME_RULES: list[OutcomeRule] = [
    _RULE_CRITICAL_CONTRADICTION,
    _RULE_PAYMENT_FAILED,
    _RULE_PAYMENT_UNRESOLVED,
    _RULE_DELIVERY_FAILED,
    _RULE_BUSINESS_FAILURE_MARKERS,
    _RULE_INVENTORY_ALLOCATION_FAILED,
    _RULE_ORDER_CANCELLED,
    _RULE_TRANSACTION_FULFILLED,
    _RULE_DELIVERY_PENDING,
    _RULE_FULFILLMENT_PENDING,
    _RULE_INSUFFICIENT_DOWNSTREAM,
]

RULE_BY_ID: dict[str, OutcomeRule] = {
    rule.rule_id: rule for rule in OUTCOME_RULES
}


def build_context(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    evidence: EvidenceReport,
    consistency: ConsistencyResult,
) -> EvaluationContext:
    """Precompute the deterministic evaluation context for a journey."""
    events_by_type: dict[str, list[JourneyEvent]] = {}
    for event in journey.chronological_events:
        events_by_type.setdefault(event.event_type, []).append(event)
    return EvaluationContext(
        journey=journey,
        integrity=integrity,
        evidence=evidence,
        consistency=consistency,
        present_types=set(events_by_type.keys()),
        events_by_type=events_by_type,
    )