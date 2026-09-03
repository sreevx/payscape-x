"""Tests for Part 3 journey reconstruction, integrity detection and graph.

Covers: chronological reconstruction, ingestion-order preservation,
duplicate detection, delayed detection, missing-event candidates,
contradiction detection, out-of-order detection, orphan/unknown detection,
graph node/edge generation, deterministic output and all 10 Part 2
scenarios. No business-outcome rules — the engine describes what happened.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.enums import EventSource
from app.core.events import EventType
from app.journey import integrity as integrity_module
from app.journey.graph import build
from app.journey.integrity import analyze
from app.journey.reconstructor import JourneyEvent, reconstruct
from app.models import ScenarioInstance, TransactionEvent
from app.synthetic.scenarios import SCENARIO_DEFINITIONS
from tests.seed_helpers import build_seeded_engine

SCENARIO_BY_TYPE = {definition.scenario_type.value: definition for definition in SCENARIO_DEFINITIONS}

# Last event type expected for the FIRST journey of each scenario (seed 42).
EXPECTED_LAST_EVENT = {
    "NORMAL_SUCCESS": "DELIVERY_COMPLETED",
    "PAYMENT_FAILED": "ORDER_CANCELLED",
    "DUPLICATE_WEBHOOK": "DELIVERY_COMPLETED",
    "DELAYED_WEBHOOK": "DELIVERY_COMPLETED",
    "INVENTORY_FAILURE": "NO_FULFILLMENT",
    "DELIVERY_FAILURE": "CUSTOMER_MESSAGE_RECEIVED",
    "REFUND_FLOW": "PAYMENT_REFUNDED",
    "MISSING_EVENT": "PAYMENT_CAPTURED",
    "CONTRADICTORY_EVENT": "WEBHOOK_RECEIVED",
    "COMPOUND_FAILURE": "CUSTOMER_COMPLAINT",
}


@pytest.fixture(scope="module")
def seeded():
    engine, factory = build_seeded_engine()
    yield factory
    engine.dispose()


@pytest.fixture(scope="module")
def first_journey_ids(seeded):
    """payment_id of the first generated journey per scenario type."""
    with seeded() as session:
        result = {}
        for instance in session.scalars(select(ScenarioInstance)):
            if instance.scenario_type.value not in result:
                result[instance.scenario_type.value] = instance.metadata_["payment_id"]
        return result


def _reconstruct(seeded, payment_id: str):
    with seeded() as session:
        return analyze_with_session(session, payment_id)


# ---------------------------------------------------------------------------
# Chronological reconstruction
# ---------------------------------------------------------------------------

def test_normal_success_journey_reconstructed(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["NORMAL_SUCCESS"])
    events = journey.chronological_events
    assert len(events) == 17
    # Chronological by construction.
    stamps = [event.timestamp for event in events]
    assert stamps == sorted(stamps)
    # Every event shares the journey correlation.
    assert len({event.correlation_id for event in events}) == 1
    assert journey.correlation_id == events[0].correlation_id
    assert events[0].event_type == "ORDER_CREATED"
    assert events[-1].event_type == "DELIVERY_COMPLETED"
    # Full happy-path chain is present in order (17 events, one per stage).
    chain = [event.event_type for event in events]
    expected = [
        "ORDER_CREATED", "PAYMENT_CREATED", "PAYMENT_AUTHORIZED", "PAYMENT_CAPTURED",
        "WEBHOOK_SENT", "WEBHOOK_RECEIVED", "ORDER_CONFIRMED", "INVENTORY_RESERVED",
        "FULFILLMENT_CREATED", "FULFILLMENT_PROCESSING", "FULFILLMENT_PACKED",
        "FULFILLMENT_SHIPPED", "INVENTORY_DECREMENTED", "SHIPMENT_CREATED",
        "SHIPMENT_IN_TRANSIT", "DELIVERY_OUT_FOR_DELIVERY", "DELIVERY_COMPLETED",
    ]
    position = {event_type: index for index, event_type in enumerate(chain)}
    assert sorted(position.values()) == list(range(len(chain)))  # types unique
    assert chain == expected


def test_ingestion_order_preserved(seeded, first_journey_ids):
    journey, _integrity, _graph = _reconstruct(seeded, first_journey_ids["NORMAL_SUCCESS"])
    # The synthetic dataset appends events chronologically, so ingestion
    # order == chronological order; the positions must line up.
    for position, event in enumerate(journey.ingestion_events):
        assert event.ingestion_position == position
    # And the chronological view exposes the same positions.
    assert [event.ingestion_position for event in journey.chronological_events] == list(
        range(len(journey.chronological_events))
    )


def test_unknown_transaction_returns_none(seeded):
    with seeded() as session:
        assert reconstruct(session, uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# Integrity detection
# ---------------------------------------------------------------------------

def test_duplicate_detection_duplicate_webhook(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["DUPLICATE_WEBHOOK"])
    assert integrity.duplicate_count >= 1
    rule_ids = {item.rule_id for item in integrity.duplicates}
    assert "DUPLICATE_IDEMPOTENCY_KEY" in rule_ids
    assert "DUPLICATE_WEBHOOK_ROW" in rule_ids
    # The duplicated unified event is flagged and points at the canonical one.
    flagged = [event for event in journey.chronological_events if event.is_duplicate]
    assert flagged
    assert all(event.duplicate_of_event_id for event in flagged)
    # Nothing was deleted — both deliveries remain in the stream.
    types = {event.event_type for event in journey.chronological_events}
    assert "WEBHOOK_RECEIVED" in types and "WEBHOOK_DUPLICATE" in types


def test_delayed_event_detection(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["DELAYED_WEBHOOK"])
    assert integrity.delayed_count >= 1
    types = {event.event_type for event in journey.chronological_events}
    assert "WEBHOOK_DELAYED" in types
    delayed_types = {item.event_type for item in integrity.delayed_events}
    assert delayed_types  # WEBHOOK_DELAYED and/or DELAYED webhook rows


def test_missing_event_candidates(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["MISSING_EVENT"])
    candidates = [item.event_type for item in integrity.missing_expected_event_candidates]
    assert "WEBHOOK_RECEIVED" in candidates  # captured but webhook never arrived
    # Structural observation only — no outcome classification anywhere.
    assert "PAYMENT_FAILED" not in candidates
    types = {event.event_type for event in journey.chronological_events}
    assert "WEBHOOK_RECEIVED" not in types  # genuinely absent, not repaired


def test_contradiction_detection(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["CONTRADICTORY_EVENT"])
    contradictions = integrity.contradictions
    assert contradictions
    payment_contradiction = next(
        item for item in contradictions if item.type == "PAYMENT_STATE_CONTRADICTION"
    )
    assert payment_contradiction.rule_id == "PAYMENT_CAPTURED_AND_FAILED"
    assert len(payment_contradiction.involved_event_ids) == 2
    assert len(payment_contradiction.timestamps) == 2
    assert "PAYMENT_CAPTURED" in payment_contradiction.explanation
    # Both events preserved in the stream — neither deleted nor resolved.
    types = {event.event_type for event in journey.chronological_events}
    assert "PAYMENT_CAPTURED" in types and "PAYMENT_FAILED" in types


def test_compound_failure_missing_candidates(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["COMPOUND_FAILURE"])
    candidates = {
        (item.event_type, item.rule_id)
        for item in integrity.missing_expected_event_candidates
    }
    assert ("ORDER_CONFIRMED", "MISSING_CONFIRMATION_AFTER_CAPTURE") in candidates
    assert ("FULFILLMENT_CREATED", "MISSING_FULFILLMENT_AFTER_RESERVATION") in candidates
    # The compound chain reads exactly as generated.
    chain = [event.event_type for event in journey.chronological_events]
    assert chain[-1] == "CUSTOMER_COMPLAINT"
    assert "PAYMENT_CAPTURED" in chain
    assert "WEBHOOK_DELAYED" in chain
    assert "ORDER_NOT_CONFIRMED" in chain
    assert "INVENTORY_RESERVATION_EXPIRED" in chain
    assert "INVENTORY_OUT_OF_STOCK" in chain
    assert "NO_FULFILLMENT" in chain
    # Structural only — no outcome classification.
    assert not integrity.contradictions


def test_delivery_failure_journey(seeded, first_journey_ids):
    journey, integrity, _graph = _reconstruct(seeded, first_journey_ids["DELIVERY_FAILURE"])
    chain = [event.event_type for event in journey.chronological_events]
    for expected in ("PAYMENT_CAPTURED", "ORDER_CONFIRMED", "INVENTORY_RESERVED",
                     "FULFILLMENT_CREATED", "FULFILLMENT_SHIPPED", "SHIPMENT_CREATED",
                     "DELIVERY_FAILED"):
        assert expected in chain, expected
    assert "DELIVERY_RETURNED" in chain
    assert chain[-1] == "CUSTOMER_MESSAGE_RECEIVED"


def test_out_of_order_detection(first_journey_ids):
    payment_id = first_journey_ids["NORMAL_SUCCESS"]
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            journey = reconstruct(session, uuid.UUID(payment_id))
            # Inject an event ingested LATER (high ingestion sequence) but
            # timestamped BEFORE everything else — a backlogged webhook
            # persisted out of order.
            session.add(
                TransactionEvent(
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.WEBHOOK_RECEIVED,
                    source=EventSource.WEBHOOK,
                    timestamp=journey.first_event_at - timedelta(minutes=5),
                    correlation_id=uuid.UUID(journey.correlation_id),
                    idempotency_key=f"late-{uuid.uuid4()}",
                    payload={"provider_event_id": "evt_late"},
                    ingestion_sequence=99_999,
                )
            )
            session.commit()
            journey2, integrity, _graph = analyze_with_session(session, payment_id)
            assert integrity.out_of_order_count >= 1
            item = integrity.out_of_order_events[0]
            assert item.event_type == "WEBHOOK_RECEIVED"
            assert item.ingestion_position > item.chronological_position
            # The raw timestamp was NOT mutated.
            first = journey2.chronological_events[0]
            assert first.timestamp == journey.first_event_at - timedelta(minutes=5)
    finally:
        engine.dispose()


def test_orphan_event_detection(first_journey_ids):
    payment_id = first_journey_ids["NORMAL_SUCCESS"]
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            journey = reconstruct(session, uuid.UUID(payment_id))
            stray_correlation = uuid.uuid4()
            session.add(
                TransactionEvent(
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.CUSTOMER_MESSAGE_RECEIVED,
                    source=EventSource.CUSTOMER,
                    timestamp=journey.last_event_at + timedelta(minutes=1),
                    correlation_id=stray_correlation,
                    payload={"channel": "CHAT"},
                    ingestion_sequence=99_998,
                )
            )
            session.commit()
            _journey2, integrity, _graph = analyze_with_session(session, payment_id)
            assert integrity.orphan_count >= 1
            orphan = integrity.orphan_events[0]
            assert orphan.correlation_id == str(stray_correlation)
            assert orphan.event_type == "CUSTOMER_MESSAGE_RECEIVED"
    finally:
        engine.dispose()


def test_unknown_event_detection_unit():
    integrity = integrity_module.JourneyIntegrity(transaction_id="tx-1", total_events=1, linked_events=1)
    event = JourneyEvent(
        event_id="evt-x",
        order_id="o-1",
        payment_id="p-1",
        event_type="MYSTERY_EVENT",
        source="WEBHOOK",
        timestamp=datetime(2026, 8, 24, tzinfo=timezone.utc),
        correlation_id="c-1",
        idempotency_key=None,
        payload={},
        ingestion_position=0,
    )
    integrity_module._detect_unknowns([event], integrity)
    assert event.is_unknown is True
    assert len(integrity.unknown_events) == 1
    assert integrity.unknown_events[0].event_type == "MYSTERY_EVENT"


def test_synthetic_journeys_have_no_unknown_events(seeded, first_journey_ids):
    for scenario_type in first_journey_ids:
        _journey, integrity, _graph = _reconstruct(seeded, first_journey_ids[scenario_type])
        assert integrity.unknown_count == 0, scenario_type


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def test_graph_node_generation(seeded, first_journey_ids):
    journey, _integrity, graph = _reconstruct(seeded, first_journey_ids["NORMAL_SUCCESS"])
    kinds = {node.kind for node in graph.nodes}
    assert kinds == {"journey_root", "correlation_root", "event"}
    event_nodes = [node for node in graph.nodes if node.kind == "event"]
    assert len(event_nodes) == journey.total_events
    for node in event_nodes:
        assert node.event_type
        assert node.timestamp is not None
        assert node.source
        assert node.correlation_id == journey.correlation_id
        assert node.payload_ref == node.id
        assert "x" in node.position and "y" in node.position


def test_graph_edge_generation(seeded, first_journey_ids):
    journey, _integrity, graph = _reconstruct(seeded, first_journey_ids["NORMAL_SUCCESS"])
    relationship_types = {edge.relationship_type for edge in graph.edges}
    assert relationship_types == {
        "PRECEDES", "TRIGGERS", "BELONGS_TO", "CORRELATES_WITH", "DERIVED_FROM",
    }
    # One BELONGS_TO per event, one PRECEDES per adjacent pair.
    belongs = [edge for edge in graph.edges if edge.relationship_type == "BELONGS_TO"]
    precedes = [edge for edge in graph.edges if edge.relationship_type == "PRECEDES"]
    assert len(belongs) == journey.total_events
    assert len(precedes) == journey.total_events - 1
    # Triggers include the payment -> webhook -> confirmation chain.
    trigger_rules = {edge.rule_id for edge in graph.edges if edge.relationship_type == "TRIGGERS"}
    assert "TRIGGERS:PAYMENT_CAPTURED:WEBHOOK_SENT" in trigger_rules
    assert "TRIGGERS:WEBHOOK_RECEIVED:ORDER_CONFIRMED" in trigger_rules
    # Derived edges exist (received derives from sent via provider event id).
    derived = [edge for edge in graph.edges if edge.relationship_type == "DERIVED_FROM"]
    assert any(edge.rule_id == "RECEIVED_DERIVED_FROM_SENT" for edge in derived)
    # Every edge is explainable.
    for edge in graph.edges:
        assert edge.rule_id and edge.reason


def test_graph_deterministic(seeded, first_journey_ids):
    _j1, _i1, graph1 = _reconstruct(seeded, first_journey_ids["COMPOUND_FAILURE"])
    _j2, _i2, graph2 = _reconstruct(seeded, first_journey_ids["COMPOUND_FAILURE"])
    nodes1 = [(node.id, node.kind, node.label, node.position) for node in graph1.nodes]
    nodes2 = [(node.id, node.kind, node.label, node.position) for node in graph2.nodes]
    edges1 = [(edge.source, edge.target, edge.relationship_type, edge.rule_id) for edge in graph1.edges]
    edges2 = [(edge.source, edge.target, edge.relationship_type, edge.rule_id) for edge in graph2.edges]
    assert nodes1 == nodes2
    assert edges1 == edges2


def test_deterministic_reconstruction_across_runs(first_journey_ids):
    engine_a, factory_a = build_seeded_engine(seed=42)
    engine_b, factory_b = build_seeded_engine(seed=42)
    payment_id = first_journey_ids["NORMAL_SUCCESS"]
    try:
        with factory_a() as session:
            journey_a = reconstruct(session, uuid.UUID(payment_id))
            chain_a = [(e.event_type, e.timestamp.isoformat(), e.ingestion_position)
                       for e in journey_a.chronological_events]
        with factory_b() as session:
            journey_b = reconstruct(session, uuid.UUID(payment_id))
            chain_b = [(e.event_type, e.timestamp.isoformat(), e.ingestion_position)
                       for e in journey_b.chronological_events]
        assert chain_a == chain_b
    finally:
        engine_a.dispose()
        engine_b.dispose()


# ---------------------------------------------------------------------------
# All 10 scenarios
# ---------------------------------------------------------------------------

def test_all_scenarios_reconstruct(seeded, first_journey_ids):
    assert set(first_journey_ids.keys()) == set(EXPECTED_LAST_EVENT.keys())
    for scenario_type, payment_id in first_journey_ids.items():
        journey, integrity, graph = _reconstruct(seeded, payment_id)
        events = journey.chronological_events
        assert events, scenario_type
        # Chronological.
        stamps = [event.timestamp for event in events]
        assert stamps == sorted(stamps), scenario_type
        # One correlation per journey.
        assert len({event.correlation_id for event in events}) == 1, scenario_type
        # Every journey starts with ORDER_CREATED.
        assert events[0].event_type == "ORDER_CREATED", scenario_type
        # Last event matches the generated narrative.
        assert events[-1].event_type == EXPECTED_LAST_EVENT[scenario_type], scenario_type
        # Integrity is internally consistent.
        assert integrity.total_events == len(events), scenario_type
        assert integrity.linked_events <= integrity.total_events, scenario_type
        assert 0 <= integrity.orphan_count <= integrity.total_events, scenario_type
        # Graph is well-formed.
        assert graph.nodes and graph.edges, scenario_type
        event_nodes = [node for node in graph.nodes if node.kind == "event"]
        assert len(event_nodes) == len(events), scenario_type
        assert all(edge.rule_id for edge in graph.edges), scenario_type


def analyze_with_session(session, payment_id):
    """Reconstruct + analyze using an already-open session."""
    from app.services.journeys_service import _load_webhooks

    journey = reconstruct(session, uuid.UUID(payment_id))
    integrity = analyze(journey, _load_webhooks(session, uuid.UUID(payment_id)))
    graph = build(journey)
    return journey, integrity, graph