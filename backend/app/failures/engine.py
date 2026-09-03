"""Compound Failure decision engine (Part 6).

Deterministic analysis of ONE transaction's failure structure. It consumes
the Part 3 journey + integrity, Part 4 evidence/consistency and the Part 5
outcome — it never recomputes or replaces the outcome.

Pipeline (documented in docs/architecture.md):

    journey + evidence + consistency + outcome
        -> detect chain nodes (OBSERVED from records, DERIVED from absence)
        -> order nodes along the promise-chain axis (stage, then time)
        -> connect consecutive nodes via CHAIN_RULES
        -> pick root cause(s) (OBSERVED nodes only, explicit priority)
        -> decide "detected" = definitive FAILED outcome + >= 2 chain nodes
           across >= 2 distinct stages
        -> severity / confidence / classification (all deterministic)

The engine describes what happened. It does NOT predict what happens next
(POTENTIAL consequences live in the impact engine) and it never invents a
causal chain when the outcome is UNVERIFIABLE or the records only show a
single-stage failure.
"""

import uuid
from datetime import datetime
from typing import Optional

from app.consistency.models import ConsistencyResult
from app.core.events import EventType
from app.evidence.models import (
    STRENGTH_CORROBORATED,
    STRENGTH_DIRECT,
    EvidenceReport,
)
from app.failures.models import (
    CLASS_DERIVED,
    CLASS_OBSERVED,
    NOT_DETECTED_NO_FAILURE_RECORDS,
    NOT_DETECTED_OUTCOME_AT_RISK,
    NOT_DETECTED_OUTCOME_FULFILLED,
    NOT_DETECTED_OUTCOME_UNVERIFIABLE,
    NOT_DETECTED_SINGLE_STAGE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    STATUS_DERIVED,
    STATUS_OBSERVED,
    ChainEdge,
    CompoundFailureResult,
    FailureNode,
    RootCause,
)
from app.failures.rules import (
    CHAIN_RULES,
    DEFAULT_REASON,
    DEFAULT_RELATIONSHIP,
    DEFAULT_RULE_ID,
    IMPACT_ABOUTS,
    NODE_KIND_BY_ID,
    NODE_KIND_DEFS,
    NON_IMPACT_ABOUTS,
    STAGE_INDEX,
    STAGE_ORDER,
    STAGE_SEVERITY,
)
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney
from app.outcome.models import (
    OUTCOME_AT_RISK,
    OUTCOME_FAILED,
    OUTCOME_FULFILLED,
    OutcomeResult,
)

NAMESPACE = uuid.NAMESPACE_URL


def _node_id(transaction_id: str, kind: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"payscape:node:{transaction_id}:{kind}"))


def _edge_id(transaction_id: str, source_kind: str, target_kind: str, index: int) -> str:
    return str(
        uuid.uuid5(
            NAMESPACE,
            f"payscape:chain-edge:{transaction_id}:{source_kind}:{target_kind}:{index}",
        )
    )


def _root_id(transaction_id: str, kind: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"payscape:root-cause:{transaction_id}:{kind}"))


def _compound_id(transaction_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"payscape:compound:{transaction_id}"))


def _evidence_for_events(
    evidence: EvidenceReport, event_ids: set[str]
) -> list[str]:
    """Evidence ids whose items reference any of the given events."""
    return sorted(
        {
            item.evidence_id
            for item in evidence.evidence
            if item.strength in (STRENGTH_DIRECT, STRENGTH_CORROBORATED)
            and set(item.event_ids) & event_ids
        }
    )


def _skus_of(events: list[JourneyEvent]) -> list[str]:
    skus = {
        str(event.payload.get("product_sku"))
        for event in events
        if event.payload.get("product_sku")
    }
    return sorted(skus)


def _abouts_of(events: list[JourneyEvent]) -> list[str]:
    abouts = {
        str(event.payload.get("about"))
        for event in events
        if event.payload.get("about")
    }
    return sorted(abouts)


def _message_for_kind(kind: str, present: set[str], events: list[JourneyEvent]) -> str:
    """Deterministic, record-grounded message per node kind."""
    definition = NODE_KIND_BY_ID[kind]
    skus = _skus_of(events)
    if kind == "INVENTORY_ALLOCATION_FAILED":
        message = definition.message
        if skus:
            message += f" SKU(s): {', '.join(skus)}."
        return message
    if kind == "CUSTOMER_IMPACT":
        complaint = EventType.CUSTOMER_COMPLAINT.value in present
        abouts = _abouts_of(events)
        if complaint and abouts:
            return (
                f"The customer filed a complaint about {', '.join(abouts)} "
                "(CUSTOMER_COMPLAINT recorded)."
            )
        if complaint:
            return "The customer filed a complaint (CUSTOMER_COMPLAINT recorded)."
        if abouts:
            return (
                f"The customer contacted support about {', '.join(abouts)}."
            )
        return "The customer signalled a problem with the transaction."
    return definition.message


def _events_by_type(journey: ReconstructedJourney) -> dict[str, list[JourneyEvent]]:
    by_type: dict[str, list[JourneyEvent]] = {}
    for event in journey.chronological_events:
        by_type.setdefault(event.event_type, []).append(event)
    return by_type


def _detect_nodes(
    journey: ReconstructedJourney,
    evidence: EvidenceReport,
    present: set[str],
    events_by_type: dict[str, list[JourneyEvent]],
    captured: bool,
) -> list[FailureNode]:
    """Create the failure-chain nodes evidenced by this journey.

    OBSERVED nodes come from the recorded event stream. A DERIVED node is
    only created from a documented absence (fulfillment shipped with no
    shipment/delivery records). Nothing is inferred from missing evidence
    beyond that structural rule.
    """
    nodes: list[FailureNode] = []
    for definition in NODE_KIND_DEFS:
        kind = definition.kind
        node_events: list[JourneyEvent] = []
        events: list[JourneyEvent] = []
        for event_type in definition.observed_types:
            events.extend(events_by_type.get(event_type, []))

        # ORDER_CANCELLED is only a chain node when it happens AFTER a
        # capture. A cancellation that merely follows a terminal payment
        # failure is a consequence of that failure (impact engine), not an
        # independent node.
        if kind == "ORDER_CANCELLED_AFTER_CAPTURE":
            if not events or not captured:
                continue

        # CUSTOMER_IMPACT: complaints always count; messages count only when
        # they are about a problem (routine enquiries/confirmations do not).
        if kind == "CUSTOMER_IMPACT":
            complaint_events = events_by_type.get(
                EventType.CUSTOMER_COMPLAINT.value, []
            )
            message_events = [
                event
                for event in events_by_type.get(
                    EventType.CUSTOMER_MESSAGE_RECEIVED.value, []
                )
                if str(event.payload.get("about", "")) not in NON_IMPACT_ABOUTS
            ]
            events = sorted(
                complaint_events + message_events,
                key=lambda event: (event.timestamp, event.event_id),
            )
            if not events:
                continue

        if events:
            node_events = sorted(
                events, key=lambda event: (event.timestamp, event.event_id)
            )
            status = STATUS_OBSERVED
            event_ids = [event.event_id for event in node_events]
            timestamp = node_events[-1].timestamp
            metadata: dict = {}
            skus = _skus_of(node_events)
            abouts = _abouts_of(node_events)
            if skus:
                metadata["skus"] = skus
            if abouts:
                metadata["abouts"] = abouts
            # Complaints raise the customer-impact weight deterministically.
            if kind == "CUSTOMER_IMPACT":
                metadata["has_complaint"] = any(
                    event.event_type == EventType.CUSTOMER_COMPLAINT.value
                    for event in node_events
                )
        else:
            if not definition.derived_requires:
                continue
            # DERIVED node: the block of lifecycle events that would prove
            # this stage ran is entirely absent.
            required_absent = {
                event_type for event_type in definition.derived_requires
            }
            if required_absent & present:
                continue  # some proof exists, so absence cannot be claimed
            # A derived fulfillment->shipment gap is only meaningful when the
            # fulfillment stage actually started.
            if kind == "SHIPMENT_NOT_CREATED":
                fulfillment_started = (
                    EventType.FULFILLMENT_CREATED.value in present
                    or EventType.FULFILLMENT_SHIPPED.value in present
                )
                if not fulfillment_started:
                    continue
            status = STATUS_DERIVED
            event_ids = []
            timestamp = None
            metadata = {}

        nodes.append(
            FailureNode(
                node_id=_node_id(journey.transaction_id, kind),
                kind=kind,
                stage=definition.stage,
                label=definition.label,
                status=status,
                message=_message_for_kind(kind, present, node_events),
                rule_id=(
                    f"NODE_OBSERVED_{kind}"
                    if status == STATUS_OBSERVED
                    else f"NODE_DERIVED_{kind}"
                ),
                event_ids=event_ids,
                evidence_ids=_evidence_for_events(evidence, set(event_ids)),
                timestamp=timestamp,
                metadata=metadata,
            )
        )
    return nodes


def _order_nodes(nodes: list[FailureNode]) -> list[FailureNode]:
    """Chain order: promise-chain stage first, then earliest evidence."""
    return sorted(
        nodes,
        key=lambda node: (
            STAGE_INDEX.get(node.stage, len(STAGE_ORDER)),
            node.timestamp or datetime.max,
            node.kind,
        ),
    )


def _connect(
    transaction_id: str, chain: list[FailureNode]
) -> list[ChainEdge]:
    """Deterministic edges between consecutive chain nodes."""
    edges: list[ChainEdge] = []
    for index, (source, target) in enumerate(zip(chain, chain[1:])):
        rule = None
        for candidate in CHAIN_RULES:
            if (
                source.kind in candidate.source_kinds
                and target.kind in candidate.target_kinds
            ):
                rule = candidate
                break
        edges.append(
            ChainEdge(
                edge_id=_edge_id(
                    transaction_id, source.kind, target.kind, index
                ),
                source_node=source.node_id,
                target_node=target.node_id,
                relationship_type=(
                    rule.relationship_type
                    if rule
                    else DEFAULT_RELATIONSHIP
                ),
                rule_id=rule.rule_id if rule else DEFAULT_RULE_ID,
                reason=rule.reason if rule else DEFAULT_REASON,
            )
        )
    return edges


# Root-cause preference: the kind that best explains the chain, in explicit
# priority order. Webhook delay is a contributing factor, never a root cause
# when a business-stage failure exists; impact/derived nodes are never roots.
ROOT_PRIORITY: dict[str, int] = {
    "PAYMENT_FAILED": 10,
    "INVENTORY_ALLOCATION_FAILED": 9,
    "INVENTORY_RESERVATION_EXPIRED": 9,
    "FULFILLMENT_NOT_CREATED": 8,
    "FULFILLMENT_FAILED": 8,
    "DELIVERY_FAILED": 7,
    "ORDER_NOT_CONFIRMED": 6,
    "ORDER_CANCELLED_AFTER_CAPTURE": 5,
    "WEBHOOK_DELAYED": 4,
}

ROOT_EXPLANATION: dict[str, str] = {
    "PAYMENT_FAILED": (
        "The payment failed and was never captured — the business "
        "transaction could not start its promise chain."
    ),
    "INVENTORY_ALLOCATION_FAILED": (
        "Stock could not be allocated for the paid order — the definitive "
        "blocking failure from which no fulfillment could follow."
    ),
    "INVENTORY_RESERVATION_EXPIRED": (
        "The held reservation expired before the order was confirmed — the "
        "stock guarantee for the paid order was lost."
    ),
    "FULFILLMENT_NOT_CREATED": (
        "No fulfillment was ever created for the paid order, so nothing "
        "could ship or be delivered."
    ),
    "FULFILLMENT_FAILED": (
        "Fulfillment failed after the order was confirmed, so nothing could "
        "ship or be delivered."
    ),
    "DELIVERY_FAILED": (
        "Delivery definitively failed — the shipped goods never reached the "
        "customer."
    ),
    "ORDER_NOT_CONFIRMED": (
        "The order was never confirmed within its SLA, blocking every "
        "downstream fulfilment stage."
    ),
    "ORDER_CANCELLED_AFTER_CAPTURE": (
        "The paid order was cancelled and never delivered; the transaction "
        "was reversed."
    ),
    "WEBHOOK_DELAYED": (
        "The provider webhook delay stalled order processing; treated as a "
        "contributing factor rather than the definitive business failure."
    ),
}


def _select_root_causes(
    transaction_id: str, chain: list[FailureNode]
) -> list[RootCause]:
    """Deterministic root-cause selection.

    Only OBSERVED business-stage nodes are candidates. The root is the
    candidate with the highest ROOT_PRIORITY; ties resolve toward the node
    further down the chain (the final blocking state, e.g. the out-of-stock
    allocation rather than the earlier reservation expiry). Additional
    equally-prioritised roots of the same stage are not duplicated.
    """
    candidates = [
        node
        for node in chain
        if node.status == STATUS_OBSERVED and node.kind in ROOT_PRIORITY
    ]
    if not candidates:
        return []
    best_priority = max(ROOT_PRIORITY[node.kind] for node in candidates)
    pool = [
        node for node in candidates if ROOT_PRIORITY[node.kind] == best_priority
    ]
    pool = sorted(pool, key=lambda node: chain.index(node), reverse=True)
    chosen = pool[0]
    return [
        RootCause(
            root_cause_id=_root_id(transaction_id, chosen.kind),
            kind=chosen.kind,
            label=chosen.label,
            stage=chosen.stage,
            explanation=ROOT_EXPLANATION[chosen.kind],
            rule_id="ROOT_CAUSE_PRIORITY_SELECTION",
            event_ids=chosen.event_ids,
            evidence_ids=chosen.evidence_ids,
        )
    ]


SEVERITY_LADDER = [
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
]


def _severity(
    chain: list[FailureNode], distinct_stages: int, complaint: bool
) -> str:
    """Deterministic severity: max severity of the involved stages, raised
    by the depth and customer impact of the chain."""
    max_severity = max(
        (
            SEVERITY_LADDER.index(
                STAGE_SEVERITY.get(node.stage, SEVERITY_MEDIUM)
            )
            for node in chain
        ),
        default=SEVERITY_LADDER.index(SEVERITY_LOW),
    )
    if distinct_stages >= 4:
        return SEVERITY_CRITICAL
    if distinct_stages >= 3 and complaint:
        return SEVERITY_CRITICAL
    return SEVERITY_LADDER[max_severity]


def analyze(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    evidence: EvidenceReport,
    consistency: ConsistencyResult,
    outcome: OutcomeResult,
) -> CompoundFailureResult:
    """Analyze the compound-failure structure of one transaction."""
    transaction_id = journey.transaction_id
    present = {event.event_type for event in journey.chronological_events}
    events_by_type = _events_by_type(journey)
    captured = EventType.PAYMENT_CAPTURED.value in present

    # The compound engine only reasons over definitive business failures.
    # UNVERIFIABLE / AT_RISK / FULFILLED journeys are reported undetected
    # with an explicit reason — uncertainty is never dressed up as a chain.
    if outcome.outcome == OUTCOME_FULFILLED:
        return _undetected(
            transaction_id, NOT_DETECTED_OUTCOME_FULFILLED,
            "The business transaction was fulfilled (delivered) — no failure chain exists.",
        )
    if outcome.outcome == OUTCOME_AT_RISK:
        return _undetected(
            transaction_id, NOT_DETECTED_OUTCOME_AT_RISK,
            "The transaction is at risk but not definitively failed — no compound "
            "failure chain is asserted while completion remains possible.",
        )
    if outcome.outcome != OUTCOME_FAILED:
        return _undetected(
            transaction_id, NOT_DETECTED_OUTCOME_UNVERIFIABLE,
            "The outcome is unverifiable — the records do not support a "
            "definitive failure chain.",
        )

    nodes = _detect_nodes(journey, evidence, present, events_by_type, captured)
    chain = _order_nodes(nodes)

    if not chain:
        return _undetected(
            transaction_id, NOT_DETECTED_NO_FAILURE_RECORDS,
            "The transaction failed but no chain-node records were found — "
            "nothing beyond the outcome itself can be asserted.",
        )

    # Compound = at least two chain nodes spanning at least two distinct
    # promise stages. A lone PAYMENT_FAILED or ORDER_CANCELLED is a
    # single-stage business failure, not a compound one.
    distinct_stages = {node.stage for node in chain}
    compound = len(chain) >= 2 and len(distinct_stages) >= 2

    edges = _connect(transaction_id, chain) if compound else []
    root_causes = _select_root_causes(transaction_id, chain)

    complaint = any(
        node.kind == "CUSTOMER_IMPACT"
        and node.metadata.get("has_complaint")
        for node in chain
    )
    if compound:
        severity = _severity(chain, len(distinct_stages), complaint)
    else:
        # A single-stage FAILED transaction is still a business failure
        # (MEDIUM); FULFILLED/UNVERIFIABLE/AT_RISK report LOW (no chain).
        severity = SEVERITY_MEDIUM

    event_ids = sorted({event_id for node in chain for event_id in node.event_ids})
    evidence_ids = sorted(
        {evidence_id for node in chain for evidence_id in node.evidence_ids}
    )
    all_observed = all(node.status == STATUS_OBSERVED for node in chain)
    classification = CLASS_OBSERVED if all_observed else CLASS_DERIVED

    # Deterministic confidence: base on the outcome's confidence; derived
    # chain steps lower it because the derived claim is weaker than records.
    confidence = round(outcome.confidence, 2)
    if not all_observed:
        confidence = round(confidence * 0.9, 2)

    reason = (
        "MULTI_STAGE_FAILURE_CHAIN"
        if compound
        else NOT_DETECTED_SINGLE_STAGE
    )

    primary_failure = None
    if chain:
        primary_kind = root_causes[0].kind if root_causes else None
        primary_failure = next(
            (node for node in chain if node.kind == primary_kind),
            chain[0],
        )

    return CompoundFailureResult(
        compound_failure_id=_compound_id(transaction_id),
        transaction_id=transaction_id,
        detected=compound,
        reason=reason,
        severity=severity,
        classification=classification,
        primary_failure=primary_failure,
        failure_chain=chain,
        edges=edges,
        root_causes=root_causes,
        confidence=confidence,
        event_ids=event_ids,
        evidence_ids=evidence_ids,
        metadata={
            "outcome": outcome.outcome,
            "outcome_reason_code": outcome.primary_reason.code,
            "distinct_stages": sorted(distinct_stages),
            "chain_rule_ids": [edge.rule_id for edge in edges],
        },
    )


def _undetected(
    transaction_id: str, reason: str, message: str
) -> CompoundFailureResult:
    return CompoundFailureResult(
        compound_failure_id=_compound_id(transaction_id),
        transaction_id=transaction_id,
        detected=False,
        reason=reason,
        severity=SEVERITY_LOW,
        classification=CLASS_OBSERVED,
        metadata={"note": message},
    )
