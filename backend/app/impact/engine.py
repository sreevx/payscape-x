"""Consequence / Impact decision engine (Part 6).

Deterministic analysis of ONE transaction's downstream consequences. It
consumes the reconstructed journey, the Part 4 evidence report, the Part 5
outcome, the Part 6 compound-failure result and (optionally) pre-loaded
cross-transaction facts — it never recomputes the outcome and never touches
the database itself.

Semantic separation (documented in docs/architecture.md):

  OBSERVED  — the consequence is stated by a record in the journey
  DERIVED   — the consequence follows deterministically from records
  POTENTIAL — a possible future state signalled by records (a complaint /
              contact without a refund) — NEVER presented as a fact

The engine only emits a consequence when the outcome is FAILED. For
FULFILLED / UNVERIFIABLE transactions nothing downstream is asserted:
absence of evidence is never dressed up as impact.
"""

import uuid
from typing import Optional

from app.consistency.models import ConsistencyResult
from app.core.events import EventType
from app.evidence.models import (
    STRENGTH_CORROBORATED,
    STRENGTH_DIRECT,
    EvidenceReport,
)
from app.failures.models import (
    CompoundFailureResult,
    FailureNode,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from app.impact.models import (
    CATEGORY_CUSTOMER,
    CATEGORY_DELIVERY,
    CATEGORY_FULFILLMENT,
    CATEGORY_INVENTORY,
    CATEGORY_OPERATIONAL,
    CATEGORY_ORDER,
    CATEGORY_PAYMENT,
    CATEGORY_REFUND,
    CATEGORY_REVENUE,
    CATEGORY_SHIPMENT,
    ConsequenceItem,
    CrossTransactionView,
    ImpactResult,
    ScoreComponent,
    SCOPE_MULTI,
    SCOPE_SINGLE,
    STATUS_DERIVED,
    STATUS_OBSERVED,
    STATUS_POTENTIAL,
)
from app.impact.models import IMPACT_OBSERVED  # noqa: F401  (re-exported)
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney
from app.outcome.models import OUTCOME_FAILED, OutcomeResult

NAMESPACE = uuid.NAMESPACE_URL

# Domain stage -> consequence category (used to categorise chain nodes).
STAGE_CATEGORY: dict[str, str] = {
    "PAYMENT": CATEGORY_PAYMENT,
    "WEBHOOK": CATEGORY_OPERATIONAL,
    "ORDER": CATEGORY_ORDER,
    "INVENTORY": CATEGORY_INVENTORY,
    "FULFILLMENT": CATEGORY_FULFILLMENT,
    "SHIPMENT": CATEGORY_SHIPMENT,
    "DELIVERY": CATEGORY_DELIVERY,
    "CUSTOMER": CATEGORY_CUSTOMER,
    "REFUND": CATEGORY_REFUND,
}

# Message intents that are routine, not consequences of a failure.
ROUTINE_ABOUTS = frozenset({
    "status_enquiry",
    "confirmation",
    "refund_query",
})


def _consequence_id(transaction_id: str, rule_id: str, classification: str) -> str:
    return str(
        uuid.uuid5(
            NAMESPACE,
            f"payscape:consequence:{transaction_id}:{rule_id}:{classification}",
        )
    )


def _impact_id(transaction_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"payscape:impact:{transaction_id}"))


def _evidence_for_events(evidence: EvidenceReport, event_ids: set[str]) -> list[str]:
    return sorted(
        {
            item.evidence_id
            for item in evidence.evidence
            if item.strength in (STRENGTH_DIRECT, STRENGTH_CORROBORATED)
            and set(item.event_ids) & event_ids
        }
    )


def _events(journey: ReconstructedJourney) -> dict[str, list[JourneyEvent]]:
    by_type: dict[str, list[JourneyEvent]] = {}
    for event in journey.chronological_events:
        by_type.setdefault(event.event_type, []).append(event)
    return by_type


# ---------------------------------------------------------------------------
# Observed consequences (records)
# ---------------------------------------------------------------------------

def _node_consequence(
    transaction_id: str, evidence: EvidenceReport, node: FailureNode
) -> ConsequenceItem:
    category = STAGE_CATEGORY.get(node.stage, CATEGORY_OPERATIONAL)
    rule_id = f"NODE_OBSERVED_{node.kind}"
    return ConsequenceItem(
        consequence_id=_consequence_id(transaction_id, rule_id, STATUS_OBSERVED),
        category=category,
        claim=node.label,
        classification=STATUS_OBSERVED,
        rule_id=rule_id,
        event_ids=node.event_ids,
        evidence_ids=_evidence_for_events(evidence, set(node.event_ids)),
        metadata={"kind": node.kind, "stage": node.stage},
    )


def _extra_observed_consequences(
    transaction_id: str,
    evidence: EvidenceReport,
    present: set[str],
    by_type: dict[str, list[JourneyEvent]],
    observed_kinds: set[str],
) -> list[ConsequenceItem]:
    """Observed facts not already represented by an OBSERVED chain node."""
    items: list[ConsequenceItem] = []
    captured = EventType.PAYMENT_CAPTURED.value in present

    def add(rule_id: str, category: str, claim: str, *event_types: str) -> None:
        events: list[JourneyEvent] = []
        for event_type in event_types:
            events.extend(by_type.get(event_type, []))
        if not events:
            return
        ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))
        event_ids = [event.event_id for event in ordered]
        items.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, rule_id, STATUS_OBSERVED
                ),
                category=category,
                claim=claim,
                classification=STATUS_OBSERVED,
                rule_id=rule_id,
                event_ids=event_ids,
                evidence_ids=_evidence_for_events(evidence, set(event_ids)),
            )
        )

    # Refunds are never chain nodes — always extra observed consequences.
    add(
        "IMPACT_OBS_REFUND_INITIATED",
        CATEGORY_REFUND,
        "A refund was initiated for the captured payment",
        EventType.REFUND_INITIATED.value,
    )
    add(
        "IMPACT_OBS_REFUND_COMPLETED",
        CATEGORY_REFUND,
        "A refund was completed for the captured payment",
        EventType.REFUND_COMPLETED.value,
        EventType.PAYMENT_REFUNDED.value,
    )

    if "WEBHOOK_DELAYED" not in observed_kinds:
        add(
            "IMPACT_OBS_WEBHOOK_DELAYED",
            CATEGORY_OPERATIONAL,
            "The provider webhook arrived late relative to capture",
            EventType.WEBHOOK_DELAYED.value,
        )

    if "CUSTOMER_IMPACT" not in observed_kinds:
        complaint_events = by_type.get(EventType.CUSTOMER_COMPLAINT.value, [])
        if complaint_events:
            ordered = sorted(
                complaint_events, key=lambda event: (event.timestamp, event.event_id)
            )
            event_ids = [event.event_id for event in ordered]
            items.append(
                ConsequenceItem(
                    consequence_id=_consequence_id(
                        transaction_id, "IMPACT_OBS_COMPLAINT", STATUS_OBSERVED
                    ),
                    category=CATEGORY_CUSTOMER,
                    claim="The customer filed a complaint about the transaction",
                    classification=STATUS_OBSERVED,
                    rule_id="IMPACT_OBS_COMPLAINT",
                    event_ids=event_ids,
                    evidence_ids=_evidence_for_events(evidence, set(event_ids)),
                )
            )

    # Cancellations not already represented by an ORDER_CANCELLED chain node
    # (post-payment-failure cancellations are consequences, not chain nodes).
    cancelled = by_type.get(EventType.ORDER_CANCELLED.value, [])
    if cancelled and "ORDER_CANCELLED_AFTER_CAPTURE" not in observed_kinds:
        ordered = sorted(cancelled, key=lambda event: (event.timestamp, event.event_id))
        event_ids = [event.event_id for event in ordered]
        claim = (
            "The order was cancelled after the payment was captured"
            if captured
            else "The order was cancelled after the payment attempt failed"
        )
        items.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "IMPACT_OBS_ORDER_CANCELLED", STATUS_OBSERVED
                ),
                category=CATEGORY_ORDER,
                claim=claim,
                classification=STATUS_OBSERVED,
                rule_id="IMPACT_OBS_ORDER_CANCELLED",
                event_ids=event_ids,
                evidence_ids=_evidence_for_events(evidence, set(event_ids)),
            )
        )

    # Terminal payment failures not represented by a PAYMENT_FAILED chain
    # node (this covers journeys where no chain was built).
    if "PAYMENT_FAILED" not in observed_kinds:
        failed = by_type.get(EventType.PAYMENT_FAILED.value, [])
        if failed:
            ordered = sorted(failed, key=lambda event: (event.timestamp, event.event_id))
            event_ids = [event.event_id for event in ordered]
            items.append(
                ConsequenceItem(
                    consequence_id=_consequence_id(
                        transaction_id, "IMPACT_OBS_PAYMENT_FAILED", STATUS_OBSERVED
                    ),
                    category=CATEGORY_PAYMENT,
                    claim="The payment was declined and never captured",
                    classification=STATUS_OBSERVED,
                    rule_id="IMPACT_OBS_PAYMENT_FAILED",
                    event_ids=event_ids,
                    evidence_ids=_evidence_for_events(evidence, set(event_ids)),
                )
            )

    # Customer messages about a problem or cancellation request. When a
    # CUSTOMER_IMPACT chain node already carries the message it is not
    # repeated here — except the cancellation request that preceded an
    # order cancellation (refund-flow journeys have no customer node).
    for event in by_type.get(EventType.CUSTOMER_MESSAGE_RECEIVED.value, []):
        about = str(event.payload.get("about", ""))
        if about in ROUTINE_ABOUTS:
            continue
        if "CUSTOMER_IMPACT" in observed_kinds and about != "cancel_request":
            continue
        items.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "IMPACT_OBS_CUSTOMER_MESSAGE", STATUS_OBSERVED
                ),
                category=CATEGORY_CUSTOMER,
                claim=(
                    "The customer contacted support"
                    + (f" about {about}" if about else "")
                ),
                classification=STATUS_OBSERVED,
                rule_id="IMPACT_OBS_CUSTOMER_MESSAGE",
                event_ids=[event.event_id],
                evidence_ids=_evidence_for_events(evidence, {event.event_id}),
                metadata={"about": about},
            )
        )
    return items



# ---------------------------------------------------------------------------
# Derived + potential consequences (deterministic rules)
# ---------------------------------------------------------------------------

def _derived_and_potential(
    transaction_id: str,
    evidence: EvidenceReport,
    present: set[str],
    by_type: dict[str, list[JourneyEvent]],
    chain: list[FailureNode],
) -> tuple[list[ConsequenceItem], list[ConsequenceItem]]:
    kinds = {node.kind for node in chain}
    derived: list[ConsequenceItem] = []
    potential: list[ConsequenceItem] = []

    # Rule INVENTORY_FAILURE_BLOCKS_FULFILLMENT (derived).
    inventory_failure = bool(
        kinds & {"INVENTORY_ALLOCATION_FAILED", "INVENTORY_RESERVATION_EXPIRED"}
    )
    fulfillment_missing = bool(
        kinds & {"FULFILLMENT_NOT_CREATED", "FULFILLMENT_FAILED"}
        or EventType.NO_FULFILLMENT.value in present
        or EventType.FULFILLMENT_FAILED.value in present
    )
    if inventory_failure and fulfillment_missing:
        derived.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id,
                    "INVENTORY_FAILURE_BLOCKS_FULFILLMENT",
                    STATUS_DERIVED,
                ),
                category=CATEGORY_FULFILLMENT,
                claim=(
                    "Fulfillment could not proceed — inventory allocation for "
                    "the paid order had failed"
                ),
                classification=STATUS_DERIVED,
                rule_id="INVENTORY_FAILURE_BLOCKS_FULFILLMENT",
            )
        )

    # Rule FULFILLMENT_FAILURE_BLOCKS_SHIPMENT (derived): no fulfillment, and
    # no shipment record ever appears.
    if fulfillment_missing and EventType.SHIPMENT_CREATED.value not in present:
        derived.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id,
                    "FULFILLMENT_FAILURE_BLOCKS_SHIPMENT",
                    STATUS_DERIVED,
                ),
                category=CATEGORY_SHIPMENT,
                claim=(
                    "A shipment could not be created — no fulfillment "
                    "existed to ship"
                ),
                classification=STATUS_DERIVED,
                rule_id="FULFILLMENT_FAILURE_BLOCKS_SHIPMENT",
            )
        )

    # Rule DELIVERY_PROMISE_UNMET (derived): no completed delivery.
    no_delivery = EventType.DELIVERY_COMPLETED.value not in present
    delivery_blocked = bool(
        kinds & {"DELIVERY_FAILED", "DELIVERY_RETURNED"}
        or fulfillment_missing
        or EventType.DELIVERY_FAILED.value in present
    )
    if no_delivery and delivery_blocked:
        derived.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "DELIVERY_PROMISE_UNMET", STATUS_DERIVED
                ),
                category=CATEGORY_DELIVERY,
                claim=(
                    "The delivery promise was not met — no completed delivery "
                    "was recorded"
                ),
                classification=STATUS_DERIVED,
                rule_id="DELIVERY_PROMISE_UNMET",
            )
        )

    # Rule CUSTOMER_OUTCOME_UNMET (derived): goods never reached the customer.
    returned_or_failed = bool(
        EventType.DELIVERY_FAILED.value in present
        or EventType.DELIVERY_RETURNED.value in present
    )
    if returned_or_failed and no_delivery:
        derived.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "CUSTOMER_OUTCOME_UNMET", STATUS_DERIVED
                ),
                category=CATEGORY_CUSTOMER,
                claim=(
                    "The customer did not receive the goods — delivery failed "
                    "or was returned"
                ),
                classification=STATUS_DERIVED,
                rule_id="CUSTOMER_OUTCOME_UNMET",
            )
        )

    # Rule REFUND_REVERSES_REVENUE (derived, phrased without loss claims).
    refunded = bool(
        EventType.REFUND_COMPLETED.value in present
        or EventType.PAYMENT_REFUNDED.value in present
    )
    if refunded:
        derived.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "REFUND_REVERSES_REVENUE", STATUS_DERIVED
                ),
                category=CATEGORY_REVENUE,
                claim=(
                    "The captured amount was returned to the customer "
                    "(refund completed)"
                ),
                classification=STATUS_DERIVED,
                rule_id="REFUND_REVERSES_REVENUE",
            )
        )

    # Rule REFUND_DISPUTE_RISK (POTENTIAL — signalled, never asserted).
    customer_signal = bool(
        EventType.CUSTOMER_COMPLAINT.value in present
        or any(
            str(event.payload.get("about", "")) not in ROUTINE_ABOUTS
            for event in by_type.get(EventType.CUSTOMER_MESSAGE_RECEIVED.value, [])
        )
    )
    if customer_signal and not refunded:
        potential.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id, "IMPACT_POTENTIAL_REFUND_DISPUTE_RISK", STATUS_POTENTIAL
                ),
                category=CATEGORY_REFUND,
                claim=(
                    "Refund or dispute risk — the customer signalled a problem "
                    "and no refund has been recorded yet"
                ),
                classification=STATUS_POTENTIAL,
                rule_id="IMPACT_POTENTIAL_REFUND_DISPUTE_RISK",
            )
        )

    return derived, potential


# ---------------------------------------------------------------------------
# Impact score (transparent deterministic formula)
# ---------------------------------------------------------------------------

SEVERITY_BASE: dict[str, float] = {
    SEVERITY_CRITICAL: 60.0,
    SEVERITY_HIGH: 45.0,
    SEVERITY_MEDIUM: 25.0,
    SEVERITY_LOW: 5.0,
}

OBSERVED_WEIGHT: dict[str, float] = {
    CATEGORY_PAYMENT: 4.0,
    CATEGORY_ORDER: 8.0,
    CATEGORY_INVENTORY: 8.0,
    CATEGORY_FULFILLMENT: 8.0,
    CATEGORY_SHIPMENT: 8.0,
    CATEGORY_DELIVERY: 8.0,
    CATEGORY_CUSTOMER: 10.0,
    CATEGORY_REFUND: 15.0,
    CATEGORY_REVENUE: 5.0,
    CATEGORY_OPERATIONAL: 4.0,
}

POTENTIAL_POINTS = 3.0
SCORE_CEILING = 100.0


def _weight_for(item: ConsequenceItem) -> float:
    observed = OBSERVED_WEIGHT.get(item.category, 4.0)
    if item.classification == STATUS_OBSERVED:
        return observed
    if item.classification == STATUS_DERIVED:
        return max(2.0, observed / 2)
    return POTENTIAL_POINTS


def _next_severity(severity: str) -> str:
    ladder = [SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_HIGH, SEVERITY_CRITICAL]
    index = ladder.index(severity) if severity in ladder else 0
    return ladder[min(index + 1, len(ladder) - 1)]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def analyze(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    evidence: EvidenceReport,
    consistency: ConsistencyResult,
    outcome: OutcomeResult,
    failure: CompoundFailureResult,
    cross: Optional[CrossTransactionView] = None,
) -> ImpactResult:
    """Assess consequences + impact for one FAILED transaction."""
    transaction_id = journey.transaction_id
    present = {event.event_type for event in journey.chronological_events}
    by_type = _events(journey)

    # Impact is only asserted over definitive business failures. FULFILLED,
    # AT_RISK and UNVERIFIABLE transactions report no consequences — absence
    # of evidence is never turned into impact.
    if outcome.outcome != OUTCOME_FAILED:
        return ImpactResult(
            impact_id=_impact_id(transaction_id),
            transaction_id=transaction_id,
            scope=SCOPE_SINGLE,
            affected_transactions=0,
            affected_orders=0,
            affected_products=0,
            severity=SEVERITY_LOW,
            impact_score=0.0,
            shared_failure_patterns=[],
            metadata={"note": "no consequences asserted for a non-FAILED outcome"},
        )

    chain = failure.failure_chain
    chain_kinds = {node.kind for node in chain}
    observed_kinds = {
        node.kind for node in chain if node.status == STATUS_OBSERVED
    }

    observed: list[ConsequenceItem] = []
    for node in chain:
        # Records back the observed consequences; a DERIVED chain node is
        # reported under the derived list, never as an observed fact.
        if node.status == STATUS_OBSERVED:
            observed.append(_node_consequence(transaction_id, evidence, node))
    observed.extend(
        _extra_observed_consequences(
            transaction_id, evidence, present, by_type, observed_kinds
        )
    )
    # De-duplicate identical observed consequences (same rule_id).
    seen: set[str] = set()
    unique_observed: list[ConsequenceItem] = []
    for item in observed:
        if item.rule_id in seen:
            continue
        seen.add(item.rule_id)
        unique_observed.append(item)

    derived, potential = _derived_and_potential(
        transaction_id, evidence, present, by_type, chain
    )

    # --- Cross-transaction impact --------------------------------------
    scope = SCOPE_SINGLE
    shared_skus: list[str] = []
    affected_others: list = []
    multi_points = 0.0
    shortage_skus = cross.shortage_skus if cross else []
    if cross is not None and cross.others:
        scope = SCOPE_MULTI
        shared_skus = cross.shortage_skus
        affected_others = list(cross.others)
        multi_points = min(20.0, 5.0 * len(cross.others))
        unique_observed.append(
            ConsequenceItem(
                consequence_id=_consequence_id(
                    transaction_id,
                    "SHARED_INVENTORY_FAILURE_AFFECTS_MULTIPLE_ORDERS",
                    STATUS_OBSERVED,
                ),
                category=CATEGORY_OPERATIONAL,
                claim=(
                    f"The same SKU shortage affected {len(cross.others)} other "
                    f"transaction(s): {', '.join(cross.shortage_skus)}"
                ),
                classification=STATUS_OBSERVED,
                rule_id="SHARED_INVENTORY_FAILURE_AFFECTS_MULTIPLE_ORDERS",
                metadata={"affected_transactions": len(cross.others) + 1},
            )
        )

    # --- Severity -------------------------------------------------------
    if failure.detected:
        severity = failure.severity
    else:
        severity = SEVERITY_MEDIUM
    if scope == SCOPE_MULTI:
        severity = _next_severity(severity)

    # --- Impact score ----------------------------------------------------
    components: list[ScoreComponent] = [
        ScoreComponent(
            signal=f"SEVERITY_BASE_{severity}",
            points=SEVERITY_BASE[severity],
            note=f"deterministic severity base for {severity}",
        )
    ]
    score = SEVERITY_BASE[severity]
    for item in unique_observed:
        points = _weight_for(item)
        score += points
        components.append(
            ScoreComponent(
                signal=f"OBSERVED_{item.category}",
                points=points,
                note=item.claim,
            )
        )
    for item in derived:
        points = _weight_for(item)
        score += points
        components.append(
            ScoreComponent(
                signal=f"DERIVED_{item.category}",
                points=points,
                note=item.claim,
            )
        )
    for item in potential:
        points = _weight_for(item)
        score += points
        components.append(
            ScoreComponent(
                signal=f"POTENTIAL_{item.category}",
                points=points,
                note=item.claim,
            )
        )
    if multi_points:
        score += multi_points
        components.append(
            ScoreComponent(
                signal="MULTI_TRANSACTION",
                points=multi_points,
                note=f"{len(cross.others)} other transaction(s) share the shortage",
            )
        )
    impact_score = round(min(SCORE_CEILING, score), 1)

    # Product/sku universe for the affected cohort.
    affected_products = len(set(shortage_skus))
    if cross is not None:
        for other in cross.others:
            affected_products = max(
                affected_products, len(set(shortage_skus) | set(other.product_skus))
            )
    if scope == SCOPE_SINGLE and shortage_skus:
        affected_products = len(set(shortage_skus))

    # The impacted cohort INCLUDES the subject transaction: 1 for a
    # single-transaction failure, 1 + other members when the shortage spans
    # multiple transactions.
    affected_transactions = len(affected_others) + 1
    affected_orders = affected_transactions

    consequence_items = unique_observed + derived + potential
    event_ids = sorted(
        {event_id for item in consequence_items for event_id in item.event_ids}
    )
    evidence_ids = sorted(
        {evidence_id for item in consequence_items for evidence_id in item.evidence_ids}
    )

    return ImpactResult(
        impact_id=_impact_id(transaction_id),
        transaction_id=transaction_id,
        scope=scope,
        affected_transactions=affected_transactions,
        affected_orders=affected_orders,
        affected_products=affected_products,
        observed_consequences=unique_observed,
        derived_consequences=derived,
        potential_consequences=potential,
        severity=severity,
        impact_score=impact_score,
        shared_skus=shared_skus,
        shared_failure_patterns=(
            ["INVENTORY_OUT_OF_STOCK"] if shared_skus else []
        ),
        affected=affected_others,
        score_components=components,
        event_ids=event_ids,
        evidence_ids=evidence_ids,
        metadata={
            "outcome": outcome.outcome,
            "compound_failure_detected": failure.detected,
            "chain_node_kinds": sorted(chain_kinds),
        },
    )
