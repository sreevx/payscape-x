"""Journey reconstruction service (Part 3).

Thin composition layer between the API routes and the deterministic
`app.journey` modules: loads the payment, reconstructs the journey, runs
integrity detection, builds the graph and maps everything onto the API
schemas. Returns None for unknown transaction ids (routes turn that into
404).
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.journey import graph as graph_module
from app.journey import integrity as integrity_module
from app.journey.reconstructor import reconstruct
from app.models import Webhook
from app.schemas.journeys import (
    ContradictionItem,
    DelayedItem,
    DuplicateItem,
    GraphEdge,
    GraphNode,
    JourneyEventItem,
    JourneyGraphResponse,
    JourneyIntegrityResponse,
    JourneyResponse,
    MissingCandidateItem,
    OrphanItem,
    OutOfOrderItem,
    UnknownItem,
)


def _load_webhooks(session: Session, payment_id: uuid.UUID) -> list[Webhook]:
    return list(
        session.scalars(
            select(Webhook).where(Webhook.payment_id == payment_id)
        )
    )


def _journey_event_item(event) -> JourneyEventItem:
    return JourneyEventItem(
        id=event.event_id,
        order_id=event.order_id or "",
        payment_id=event.payment_id,
        event_type=event.event_type,
        source=event.source,
        timestamp=event.timestamp,
        correlation_id=event.correlation_id,
        idempotency_key=event.idempotency_key,
        payload=event.payload,
        ingestion_position=event.ingestion_position,
        is_duplicate=event.is_duplicate,
        is_unknown=event.is_unknown,
        is_orphan=event.is_orphan,
        duplicate_of_event_id=event.duplicate_of_event_id,
    )


def _graph_response(graph) -> JourneyGraphResponse:
    return JourneyGraphResponse(
        transaction_id=graph.transaction_id,
        correlation_id=graph.correlation_id,
        nodes=[
            GraphNode(
                id=node.id,
                kind=node.kind,
                label=node.label,
                event_type=node.event_type,
                timestamp=node.timestamp,
                source=node.source,
                correlation_id=node.correlation_id,
                payload_ref=node.payload_ref,
                position=node.position,
            )
            for node in graph.nodes
        ],
        edges=[
            GraphEdge(
                source=edge.source,
                target=edge.target,
                relationship_type=edge.relationship_type,
                rule_id=edge.rule_id,
                reason=edge.reason,
            )
            for edge in graph.edges
        ],
    )


def _integrity_response(integrity) -> JourneyIntegrityResponse:
    return JourneyIntegrityResponse(
        transaction_id=integrity.transaction_id,
        total_events=integrity.total_events,
        linked_events=integrity.linked_events,
        orphan_count=integrity.orphan_count,
        duplicate_count=integrity.duplicate_count,
        unknown_count=integrity.unknown_count,
        delayed_count=integrity.delayed_count,
        out_of_order_count=integrity.out_of_order_count,
        first_event_at=integrity.first_event_at,
        last_event_at=integrity.last_event_at,
        duration_seconds=integrity.duration_seconds,
        missing_expected_event_candidates=[
            MissingCandidateItem(
                event_type=item.event_type,
                rule_id=item.rule_id,
                note=item.note,
            )
            for item in integrity.missing_expected_event_candidates
        ],
        contradictions=[
            ContradictionItem(
                type=item.type,
                rule_id=item.rule_id,
                involved_event_ids=item.involved_event_ids,
                timestamps=item.timestamps,
                explanation=item.explanation,
            )
            for item in integrity.contradictions
        ],
        duplicates=[
            DuplicateItem(
                event_id=item.event_id,
                event_type=item.event_type,
                idempotency_key=item.idempotency_key,
                canonical_event_id=item.canonical_event_id,
                rule_id=item.rule_id,
            )
            for item in integrity.duplicates
        ],
        out_of_order_events=[
            OutOfOrderItem(
                event_id=item.event_id,
                event_type=item.event_type,
                timestamp=item.timestamp,
                ingestion_position=item.ingestion_position,
                chronological_position=item.chronological_position,
            )
            for item in integrity.out_of_order_events
        ],
        delayed_events=[
            DelayedItem(
                event_id=item.event_id,
                event_type=item.event_type,
                delay_minutes=item.delay_minutes,
            )
            for item in integrity.delayed_events
        ],
        unknown_events=[
            UnknownItem(
                event_id=item.event_id,
                event_type=item.event_type,
                reason=item.reason,
            )
            for item in integrity.unknown_events
        ],
        orphan_events=[
            OrphanItem(
                event_id=item.event_id,
                event_type=item.event_type,
                correlation_id=item.correlation_id,
                reason=item.reason,
            )
            for item in integrity.orphan_events
        ],
    )


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None


def _reconstruct_all(session: Session, transaction_id: str):
    """Reconstruct + analyze + graph. Returns None when unknown."""
    payment_uuid = _resolve_transaction_id(transaction_id)
    if payment_uuid is None:
        return None
    journey = reconstruct(session, payment_uuid)
    if journey is None:
        return None
    webhooks = _load_webhooks(session, payment_uuid)
    integrity = integrity_module.analyze(journey, webhooks)
    graph = graph_module.build(journey)
    return journey, integrity, graph


def _map_journey(journey, integrity, graph) -> JourneyResponse:
    """Map a reconstructed journey + integrity + graph onto the API schema.

    Extracted so the Part 4 analysis endpoint can reuse the same mapping
    without reconstructing the journey a second time.
    """
    return JourneyResponse(
        transaction_id=journey.transaction_id,
        order_id=journey.order_id or "",
        payment_id=journey.payment_id,
        correlation_id=journey.correlation_id,
        events=[_journey_event_item(event) for event in journey.chronological_events],
        graph=_graph_response(graph),
        integrity=_integrity_response(integrity),
    )


def get_journey(session: Session, transaction_id: str) -> Optional[JourneyResponse]:
    """Full reconstructed journey: events + graph + integrity."""
    result = _reconstruct_all(session, transaction_id)
    if result is None:
        return None
    journey, integrity, graph = result
    return _map_journey(journey, integrity, graph)


def get_journey_graph(
    session: Session, transaction_id: str
) -> Optional[JourneyGraphResponse]:
    """The deterministic journey graph only."""
    result = _reconstruct_all(session, transaction_id)
    if result is None:
        return None
    _journey, _integrity, graph = result
    return _graph_response(graph)


def get_journey_integrity(
    session: Session, transaction_id: str
) -> Optional[JourneyIntegrityResponse]:
    """The structural integrity report only."""
    result = _reconstruct_all(session, transaction_id)
    if result is None:
        return None
    _journey, integrity, _graph = result
    return _integrity_response(integrity)