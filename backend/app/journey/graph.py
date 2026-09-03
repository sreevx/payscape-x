"""Journey graph (Part 3).

Represents a reconstructed journey as a deterministic graph.

Nodes
- one JOURNEY_ROOT node (the transaction)
- one CORRELATION_ROOT node per journey correlation
- one EVENT node per unified event

Edges (deterministic relationship types, never AI-derived)
- PRECEDES        consecutive events in chronological order
- TRIGGERS        documented event-type transitions that actually occurred
- BELONGS_TO      event -> JOURNEY_ROOT
- CORRELATES_WITH event -> CORRELATION_ROOT
- DERIVED_FROM    events whose identity/payload derives from another event
                  (duplicate webhook, refund completion, received webhook)

Every edge carries `rule_id` (machine) + `reason` (human) so the graph is
explainable. Layout is a deterministic linear vertical stack — nodes carry
fixed positions derived purely from their order.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.events import EventType
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney

# Documented happy-path transitions. An edge is only added when both events
# actually exist in the journey AND the triggerer precedes the target in
# chronological order — the graph still describes what happened, it just
# annotates known relationships.
TRIGGER_MAP: dict[str, frozenset[str]] = {
    EventType.ORDER_CREATED.value: frozenset({EventType.PAYMENT_CREATED.value}),
    EventType.PAYMENT_CREATED.value: frozenset({EventType.PAYMENT_AUTHORIZED.value}),
    EventType.PAYMENT_AUTHORIZED.value: frozenset({EventType.PAYMENT_CAPTURED.value}),
    EventType.PAYMENT_CAPTURED.value: frozenset({EventType.WEBHOOK_SENT.value}),
    EventType.WEBHOOK_SENT.value: frozenset({EventType.WEBHOOK_RECEIVED.value}),
    EventType.WEBHOOK_RECEIVED.value: frozenset(
        {EventType.ORDER_CONFIRMED.value, EventType.WEBHOOK_DELAYED.value}
    ),
    EventType.ORDER_CONFIRMED.value: frozenset({EventType.INVENTORY_RESERVED.value}),
    EventType.INVENTORY_RESERVED.value: frozenset(
        {
            EventType.FULFILLMENT_CREATED.value,
            EventType.INVENTORY_DECREMENTED.value,
        }
    ),
    EventType.FULFILLMENT_CREATED.value: frozenset(
        {EventType.FULFILLMENT_PROCESSING.value}
    ),
    EventType.FULFILLMENT_PROCESSING.value: frozenset(
        {EventType.FULFILLMENT_PACKED.value}
    ),
    EventType.FULFILLMENT_PACKED.value: frozenset(
        {EventType.FULFILLMENT_SHIPPED.value}
    ),
    EventType.FULFILLMENT_SHIPPED.value: frozenset({EventType.SHIPMENT_CREATED.value}),
    EventType.SHIPMENT_CREATED.value: frozenset(
        {EventType.SHIPMENT_IN_TRANSIT.value}
    ),
    EventType.SHIPMENT_IN_TRANSIT.value: frozenset(
        {EventType.DELIVERY_OUT_FOR_DELIVERY.value}
    ),
    EventType.DELIVERY_OUT_FOR_DELIVERY.value: frozenset(
        {
            EventType.DELIVERY_COMPLETED.value,
            EventType.DELIVERY_FAILED.value,
        }
    ),
    EventType.REFUND_INITIATED.value: frozenset({EventType.REFUND_COMPLETED.value}),
    EventType.REFUND_COMPLETED.value: frozenset({EventType.PAYMENT_REFUNDED.value}),
}

# Derived-from pairs: (derived type, source type). Edge added when both exist
# and the derivation identity matches (idempotency key / provider event id).
DERIVED_FROM_RULES: list[tuple[str, str, str, str]] = [
    # (derived, source, rule_id, reason)
    (
        EventType.WEBHOOK_DUPLICATE.value,
        EventType.WEBHOOK_RECEIVED.value,
        "DUPLICATE_DERIVED_FROM_RECEIVED",
        "duplicate webhook derives from the first delivery of the same "
        "provider event id",
    ),
    (
        EventType.WEBHOOK_RECEIVED.value,
        EventType.WEBHOOK_SENT.value,
        "RECEIVED_DERIVED_FROM_SENT",
        "received webhook derives from the provider's send of the same "
        "provider event id",
    ),
    (
        EventType.REFUND_COMPLETED.value,
        EventType.REFUND_INITIATED.value,
        "REFUND_COMPLETION_DERIVED",
        "refund completion derives from the recorded refund initiation",
    ),
    (
        EventType.PAYMENT_REFUNDED.value,
        EventType.REFUND_COMPLETED.value,
        "PAYMENT_REFUNDED_DERIVED",
        "payment refunded marker derives from the completed refund",
    ),
    (
        EventType.DELIVERY_RETURNED.value,
        EventType.DELIVERY_FAILED.value,
        "RETURN_DERIVED_FROM_FAILURE",
        "delivery return derives from the recorded delivery failure",
    ),
]

NODE_SPACING = 56


@dataclass
class GraphNode:
    id: str
    kind: str  # journey_root | correlation_root | event
    label: str
    event_type: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    payload_ref: Optional[str] = None
    position: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relationship_type: str
    rule_id: str
    reason: str


@dataclass
class JourneyGraph:
    transaction_id: str
    correlation_id: Optional[str]
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


def _same_identity(a: JourneyEvent, b: JourneyEvent) -> bool:
    """Do two events share a derivation identity (idempotency/provider id)?"""
    if a.idempotency_key and a.idempotency_key == b.idempotency_key:
        return True
    provider_a = (a.payload or {}).get("provider_event_id")
    provider_b = (b.payload or {}).get("provider_event_id")
    return bool(provider_a and provider_a == provider_b)


def build(journey: ReconstructedJourney) -> JourneyGraph:
    """Build the deterministic graph for a reconstructed journey."""
    graph = JourneyGraph(
        transaction_id=journey.transaction_id,
        correlation_id=journey.correlation_id,
    )
    events = journey.chronological_events

    journey_root_id = f"journey:{journey.transaction_id}"
    graph.nodes.append(
        GraphNode(
            id=journey_root_id,
            kind="journey_root",
            label="JOURNEY",
            position={"x": 0, "y": 0},
        )
    )
    if journey.correlation_id:
        correlation_root_id = f"correlation:{journey.correlation_id}"
        graph.nodes.append(
            GraphNode(
                id=correlation_root_id,
                kind="correlation_root",
                label="CORRELATION",
                correlation_id=journey.correlation_id,
                position={"x": 0, "y": NODE_SPACING},
            )
        )

    # Event nodes + BELONGS_TO / CORRELATES_WITH edges (deterministic order).
    for index, event in enumerate(events):
        graph.nodes.append(
            GraphNode(
                id=event.event_id,
                kind="event",
                label=event.event_type,
                event_type=event.event_type,
                timestamp=event.timestamp,
                source=event.source,
                correlation_id=event.correlation_id,
                payload_ref=event.event_id,
                position={"x": 0, "y": (index + 2) * NODE_SPACING},
            )
        )
        graph.edges.append(
            GraphEdge(
                source=event.event_id,
                target=journey_root_id,
                relationship_type="BELONGS_TO",
                rule_id="EVENT_BELONGS_TO_JOURNEY",
                reason="the event belongs to this transaction journey",
            )
        )
        if journey.correlation_id:
            graph.edges.append(
                GraphEdge(
                    source=event.event_id,
                    target=correlation_root_id,
                    relationship_type="CORRELATES_WITH",
                    rule_id="EVENT_CORRELATES_WITH_CORRELATION",
                    reason="the event shares the journey correlation id",
                )
            )

    # PRECEDES: consecutive chronological events.
    for index in range(len(events) - 1):
        graph.edges.append(
            GraphEdge(
                source=events[index].event_id,
                target=events[index + 1].event_id,
                relationship_type="PRECEDES",
                rule_id="CHRONOLOGICAL_ORDER",
                reason=(
                    f"{events[index].event_type} precedes "
                    f"{events[index + 1].event_type} in chronological order"
                ),
            )
        )

    # TRIGGERS: documented transitions that actually occurred.
    by_type: dict[str, list[JourneyEvent]] = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event)
    for trigger_type, targets in TRIGGER_MAP.items():
        for trigger in by_type.get(trigger_type, []):
            for target_type in targets:
                for target in by_type.get(target_type, []):
                    if target.timestamp >= trigger.timestamp:
                        graph.edges.append(
                            GraphEdge(
                                source=trigger.event_id,
                                target=target.event_id,
                                relationship_type="TRIGGERS",
                                rule_id=f"TRIGGERS:{trigger_type}:{target_type}",
                                reason=(
                                    f"{trigger_type} triggers {target_type}"
                                ),
                            )
                        )

    # DERIVED_FROM: identity-derived relationships.
    for derived_type, source_type, rule_id, reason in DERIVED_FROM_RULES:
        for derived in by_type.get(derived_type, []):
            for source in by_type.get(source_type, []):
                if derived.event_id == source.event_id:
                    continue
                if not _same_identity(derived, source):
                    continue
                graph.edges.append(
                    GraphEdge(
                        source=derived.event_id,
                        target=source.event_id,
                        relationship_type="DERIVED_FROM",
                        rule_id=rule_id,
                        reason=reason,
                    )
                )

    return graph