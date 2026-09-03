"""Tests for the Part 5 Outcome Engine.

Covers: all 10 Part 2 scenarios, every outcome state (including AT_RISK via
a truncated injected journey), rule precedence (contradictions beat
fulfillment), resolved vs unresolved delivery contradictions, missing
evidence, compound failure, deterministic repeated execution, confidence
determinism, and evidence/event traceability back to real records.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.core.enums import EventSource
from app.core.events import EventType
from app.journey.integrity import analyze
from app.journey.reconstructor import reconstruct
from app.models import ScenarioInstance, TransactionEvent, Webhook
from app.outcome.engine import decide
from app.outcome.models import (
    OUTCOME_AT_RISK,
    OUTCOME_FAILED,
    OUTCOME_FULFILLED,
    OUTCOME_UNVERIFIABLE,
)
from app.outcome.rules import OUTCOME_RULES
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from tests.seed_helpers import build_seeded_engine

EXPECTED_OUTCOMES = {
    "NORMAL_SUCCESS": OUTCOME_FULFILLED,
    "PAYMENT_FAILED": OUTCOME_FAILED,
    "DUPLICATE_WEBHOOK": OUTCOME_FULFILLED,
    "DELAYED_WEBHOOK": OUTCOME_FULFILLED,
    "INVENTORY_FAILURE": OUTCOME_FAILED,
    "DELIVERY_FAILURE": OUTCOME_FAILED,
    "REFUND_FLOW": OUTCOME_FAILED,
    "MISSING_EVENT": OUTCOME_UNVERIFIABLE,
    "CONTRADICTORY_EVENT": OUTCOME_UNVERIFIABLE,
    "COMPOUND_FAILURE": OUTCOME_FAILED,
}

EXPECTED_PRIMARY_CODES = {
    "NORMAL_SUCCESS": "DELIVERED_TO_CUSTOMER",
    "PAYMENT_FAILED": "PAYMENT_DECLINED",
    "DUPLICATE_WEBHOOK": "DELIVERED_TO_CUSTOMER",
    "DELAYED_WEBHOOK": "DELIVERED_TO_CUSTOMER",
    "INVENTORY_FAILURE": "NO_FULFILLMENT",
    "DELIVERY_FAILURE": "DELIVERY_FAILED",
    "REFUND_FLOW": "ORDER_CANCELLED_AFTER_PAYMENT",
    "MISSING_EVENT": "INSUFFICIENT_LIFECYCLE_EVIDENCE",
    "CONTRADICTORY_EVENT": "CONTRADICTORY_RECORDS",
    "COMPOUND_FAILURE": "ORDER_NOT_CONFIRMED",
}

EXPECTED_CONFIDENCE = {
    "NORMAL_SUCCESS": 0.97,
    "PAYMENT_FAILED": 0.95,
    "DUPLICATE_WEBHOOK": 0.97,
    "DELAYED_WEBHOOK": 0.92,
    "INVENTORY_FAILURE": 0.95,
    "DELIVERY_FAILURE": 0.95,
    "REFUND_FLOW": 0.95,
    "MISSING_EVENT": 0.45,
    "CONTRADICTORY_EVENT": 0.35,
    "COMPOUND_FAILURE": 0.90,
}


@pytest.fixture(scope="module")
def seeded():
    engine, factory = build_seeded_engine()
    yield factory
    engine.dispose()


@pytest.fixture(scope="module")
def first_journey_ids(seeded):
    with seeded() as session:
        result = {}
        for instance in session.scalars(select(ScenarioInstance)):
            if instance.scenario_type.value not in result:
                result[instance.scenario_type.value] = instance.metadata_["payment_id"]
        return result


def _decide_with_session(session, payment_id: str):
    """Reconstruct + analyze + evidence + consistency + decide (one pass)."""
    journey = reconstruct(session, uuid.UUID(payment_id))
    webhooks = [
        hook
        for hook in session.scalars(select(Webhook))
        if str(hook.payment_id) == payment_id
    ]
    integrity = analyze(journey, webhooks)
    context = load_domain_context(session, uuid.UUID(payment_id))
    evidence = build_evidence(journey, integrity, context)
    consistency = build_consistency(journey, context)
    return decide(journey, integrity, evidence, consistency)


def _decide(seeded, payment_id: str):
    with seeded() as session:
        return _decide_with_session(session, payment_id)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_rule_registry_well_formed():
    assert len(OUTCOME_RULES) == 11
    priorities = [rule.priority for rule in OUTCOME_RULES]
    assert priorities == sorted(priorities)  # fixed evaluation order
    assert len({rule.rule_id for rule in OUTCOME_RULES}) == len(OUTCOME_RULES)
    for rule in OUTCOME_RULES:
        assert rule.name and rule.description, rule.rule_id
        assert rule.outcome in (
            OUTCOME_FULFILLED, OUTCOME_AT_RISK, OUTCOME_FAILED, OUTCOME_UNVERIFIABLE,
        ), rule.rule_id
        assert rule.severity in ("LOW", "MEDIUM", "HIGH"), rule.rule_id
        assert callable(rule.evaluate), rule.rule_id
        assert rule.evidence_types, rule.rule_id


# ---------------------------------------------------------------------------
# All 10 scenarios
# ---------------------------------------------------------------------------

def test_all_scenarios_classified(seeded, first_journey_ids):
    for scenario_type, payment_id in first_journey_ids.items():
        result = _decide(seeded, payment_id)
        assert result.outcome == EXPECTED_OUTCOMES[scenario_type], scenario_type
        assert result.primary_reason.code == EXPECTED_PRIMARY_CODES[scenario_type], scenario_type


def test_all_scenarios_confidence(seeded, first_journey_ids):
    for scenario_type, payment_id in first_journey_ids.items():
        result = _decide(seeded, payment_id)
        assert result.confidence == EXPECTED_CONFIDENCE[scenario_type], scenario_type
        assert 0.05 <= result.confidence <= 0.99, scenario_type


def test_compound_failure_is_business_failure_not_payment_success(seeded, first_journey_ids):
    """The flagship case: payment succeeded but the business transaction failed."""
    result = _decide(seeded, first_journey_ids["COMPOUND_FAILURE"])
    assert result.outcome == OUTCOME_FAILED
    codes = [reason.code for reason in result.reasons]
    # The whole business-level failure chain is surfaced, not the payment.
    assert "ORDER_NOT_CONFIRMED" in codes
    assert "INVENTORY_ALLOCATION_FAILED" in codes
    assert result.primary_reason.rule_id == "BUSINESS_FAILURE_MARKERS"
    # The payment itself was captured — proof this is business outcome, not
    # payment outcome.
    event_types = _journey_event_types(seeded, result)
    assert "PAYMENT_CAPTURED" in event_types
    assert result.outcome != OUTCOME_FULFILLED


def _journey_event_types(seeded, result):
    """Re-read the journey and return its event types (test helper)."""
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(result.transaction_id))
        return {event.event_type for event in journey.chronological_events}


def test_duplicate_webhook_outcome_from_business_state(seeded, first_journey_ids):
    """Duplicate existence alone must not drive the outcome — it is delivered."""
    result = _decide(seeded, first_journey_ids["DUPLICATE_WEBHOOK"])
    assert result.outcome == OUTCOME_FULFILLED
    assert result.primary_reason.code == "DELIVERED_TO_CUSTOMER"
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(first_journey_ids["DUPLICATE_WEBHOOK"]))
        types = {event.event_type for event in journey.chronological_events}
        assert "WEBHOOK_DUPLICATE" in types  # duplicates still present


def test_delayed_webhook_reflects_downstream_state(seeded, first_journey_ids):
    result = _decide(seeded, first_journey_ids["DELAYED_WEBHOOK"])
    # The webhook was delayed, but the downstream journey completed.
    assert result.outcome == OUTCOME_FULFILLED
    assert result.confidence == 0.92  # delayed-webhook adjustment applied
    signals = [adj.signal for adj in result.confidence_adjustments]
    assert "DELAYED_WEBHOOK" in signals


def test_missing_event_unverifiable(seeded, first_journey_ids):
    result = _decide(seeded, first_journey_ids["MISSING_EVENT"])
    assert result.outcome == OUTCOME_UNVERIFIABLE
    assert result.primary_reason.code == "INSUFFICIENT_LIFECYCLE_EVIDENCE"
    # Absence of downstream evidence is NOT treated as business failure.
    assert result.outcome != OUTCOME_FAILED
    # Missing evidence ids block a definitive classification.
    assert result.blocking_evidence_ids
    assert result.evidence_completeness == 0.0


def test_contradictory_event_no_unjustified_certainty(seeded, first_journey_ids):
    result = _decide(seeded, first_journey_ids["CONTRADICTORY_EVENT"])
    assert result.outcome == OUTCOME_UNVERIFIABLE
    assert result.primary_reason.code == "CONTRADICTORY_RECORDS"
    assert result.confidence == 0.35  # low — no fake certainty
    # The contradictory evidence items block classification.
    assert result.blocking_evidence_ids
    # Both sides remain referenced in the reason.
    assert len(result.primary_reason.event_ids) == 2


def test_refund_flow_outcome_from_business_state(seeded, first_journey_ids):
    result = _decide(seeded, first_journey_ids["REFUND_FLOW"])
    # The order was cancelled after payment — the transaction was reversed.
    assert result.outcome == OUTCOME_FAILED
    assert result.primary_reason.code == "ORDER_CANCELLED_AFTER_PAYMENT"
    assert "refunded" in result.primary_reason.message
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(first_journey_ids["REFUND_FLOW"]))
        types = {event.event_type for event in journey.chronological_events}
        assert "REFUND_COMPLETED" in types  # refund exists but is not the driver
    # The driver is the cancelled order state, not merely the refund.
    assert result.primary_reason.rule_id == "ORDER_CANCELLED_POST_CAPTURE"


def test_delivery_failure_failed(seeded, first_journey_ids):
    result = _decide(seeded, first_journey_ids["DELIVERY_FAILURE"])
    assert result.outcome == OUTCOME_FAILED
    assert result.primary_reason.code == "DELIVERY_FAILED"
    # The returned-goods record is part of the traced reason.
    assert result.primary_reason.event_ids
    assert result.evidence_completeness == 1.0


# ---------------------------------------------------------------------------
# Outcome states beyond the seeded dataset
# ---------------------------------------------------------------------------

def test_at_risk_when_delivery_pending_and_unresolved():
    """Truncate a delivered journey at IN_TRANSIT → AT_RISK, not UNVERIFIABLE."""
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "NORMAL_SUCCESS"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            journey = reconstruct(session, uuid.UUID(payment_id))
            # Keep everything through SHIPMENT_IN_TRANSIT; drop delivery.
            keep = True
            to_delete = []
            for event in journey.chronological_events:
                if event.event_type == "DELIVERY_OUT_FOR_DELIVERY":
                    keep = False
                if not keep:
                    to_delete.append(event.event_id)
            session.execute(
                delete(TransactionEvent).where(
                    TransactionEvent.id.in_(
                        [uuid.UUID(event_id) for event_id in to_delete]
                    )
                )
            )
            session.commit()
            result = _decide_with_session(session, payment_id)
            assert result.outcome == OUTCOME_AT_RISK
            assert result.primary_reason.code == "DELIVERY_PENDING"
            assert result.confidence == 0.60
            # The shipment progressed but the delivery group has no record.
            assert result.evidence_completeness == 0.8
            # No resolution group was observed — that is the risk.
            assert result.primary_reason.event_ids
    finally:
        engine.dispose()


def test_resolved_delivery_failure_is_fulfilled():
    """Delivery failed then delivered LATER → FULFILLED with full trace."""
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "NORMAL_SUCCESS"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            journey = reconstruct(session, uuid.UUID(payment_id))
            # Insert a DELIVERY_FAILED just before the final DELIVERY_COMPLETED.
            delivered = next(
                event for event in journey.chronological_events
                if event.event_type == "DELIVERY_COMPLETED"
            )
            from datetime import timedelta

            session.add(
                TransactionEvent(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"test:late-failure:{payment_id}"),
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.DELIVERY_FAILED,
                    source=EventSource.DELIVERY_SERVICE,
                    timestamp=delivered.timestamp - timedelta(hours=1),
                    correlation_id=uuid.UUID(journey.correlation_id),
                    idempotency_key=f"df-{payment_id}",
                    payload={"reason": "one failed attempt then redelivered"},
                    ingestion_sequence=99_999,
                )
            )
            session.commit()
            result = _decide_with_session(session, payment_id)
            # The delivery contradiction exists but is resolved by ordering.
            assert result.outcome == OUTCOME_FULFILLED
            assert result.primary_reason.code == "DELIVERED_TO_CUSTOMER"
            # 0.97 base - 2x contradicted evidence (-0.20) - out-of-order
            # injection (-0.05) = 0.72 — every penalty is traced.
            assert result.confidence == 0.72
            signals = {adj.signal for adj in result.confidence_adjustments}
            assert "CONTRADICTED_EVIDENCE" in signals
            assert "OUT_OF_ORDER_EVENTS" in signals
    finally:
        engine.dispose()


def test_unresolved_delivery_contradiction_is_unverifiable():
    """DELIVERY_COMPLETED then DELIVERY_FAILED later → contradiction blocks."""
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "NORMAL_SUCCESS"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            journey = reconstruct(session, uuid.UUID(payment_id))
            from datetime import timedelta

            delivered = next(
                event for event in journey.chronological_events
                if event.event_type == "DELIVERY_COMPLETED"
            )
            session.add(
                TransactionEvent(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"test:late-fail2:{payment_id}"),
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.DELIVERY_FAILED,
                    source=EventSource.DELIVERY_SERVICE,
                    timestamp=delivered.timestamp + timedelta(hours=1),
                    correlation_id=uuid.UUID(journey.correlation_id),
                    idempotency_key=f"df2-{payment_id}",
                    payload={"reason": "post-delivery failure record"},
                    ingestion_sequence=99_998,
                )
            )
            session.commit()
            result = _decide_with_session(session, payment_id)
            assert result.outcome == OUTCOME_UNVERIFIABLE
            assert result.primary_reason.code == "CONTRADICTORY_RECORDS"
            assert result.confidence == 0.35
    finally:
        engine.dispose()


def test_capture_failure_contradiction_beats_fulfillment():
    """Rule precedence: a payment contradiction overrides DELIVERY_COMPLETED."""
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "NORMAL_SUCCESS"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            journey = reconstruct(session, uuid.UUID(payment_id))
            from datetime import timedelta

            session.add(
                TransactionEvent(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"test:contra:{payment_id}"),
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.PAYMENT_FAILED,
                    source=EventSource.PAYMENT_PROVIDER,
                    timestamp=journey.last_event_at + timedelta(minutes=1),
                    correlation_id=uuid.UUID(journey.correlation_id),
                    idempotency_key=f"pf-{payment_id}",
                    payload={"reason": "late contradictory failure"},
                    ingestion_sequence=99_997,
                )
            )
            session.commit()
            result = _decide_with_session(session, payment_id)
            # Even though the goods were delivered, contradictory payment
            # records prevent certainty about what happened.
            assert result.outcome == OUTCOME_UNVERIFIABLE
            assert result.primary_reason.code == "CONTRADICTORY_RECORDS"
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Determinism + traceability
# ---------------------------------------------------------------------------

def test_deterministic_repeated_execution(seeded, first_journey_ids):
    import dataclasses

    for scenario_type in ("COMPOUND_FAILURE", "CONTRADICTORY_EVENT", "NORMAL_SUCCESS"):
        a = _decide(seeded, first_journey_ids[scenario_type])
        b = _decide(seeded, first_journey_ids[scenario_type])
        assert dataclasses.asdict(a) == dataclasses.asdict(b), scenario_type
        assert a.confidence == b.confidence, scenario_type


def test_deterministic_across_databases():
    import dataclasses

    payment_id = None
    engine_a, factory_a = build_seeded_engine(seed=42)
    engine_b, factory_b = build_seeded_engine(seed=42)
    try:
        with factory_a() as session:
            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "COMPOUND_FAILURE"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            result_a = _decide_with_session(session, payment_id)
        with factory_b() as session:
            result_b = _decide_with_session(session, payment_id)
        assert dataclasses.asdict(result_a) == dataclasses.asdict(result_b)
    finally:
        engine_a.dispose()
        engine_b.dispose()


def test_outcome_evidence_and_event_traceability(seeded, first_journey_ids):
    for scenario_type, payment_id in first_journey_ids.items():
        with seeded() as session:
            journey = reconstruct(session, uuid.UUID(payment_id))
            webhooks = [
                hook for hook in session.scalars(select(Webhook))
                if str(hook.payment_id) == payment_id
            ]
            integrity = analyze(journey, webhooks)
            context = load_domain_context(session, uuid.UUID(payment_id))
            evidence = build_evidence(journey, integrity, context)
            consistency = build_consistency(journey, context)
            result = decide(journey, integrity, evidence, consistency)

            known_event_ids = {event.event_id for event in journey.chronological_events}
            known_evidence_ids = {item.evidence_id for item in evidence.evidence}

            # Every referenced event/evidence id exists in the real records.
            for reason in result.reasons:
                for event_id in reason.event_ids:
                    assert event_id in known_event_ids, (scenario_type, reason.code)
                for evidence_id in reason.evidence_ids:
                    assert evidence_id in known_evidence_ids, (scenario_type, reason.code)
            for event_id in result.supporting_event_ids:
                assert event_id in known_event_ids, scenario_type
            for evidence_id in result.supporting_evidence_ids + result.blocking_evidence_ids:
                assert evidence_id in known_evidence_ids, scenario_type


def test_confidence_matches_base_plus_traced_adjustments(seeded, first_journey_ids):
    """confidence == base(outcome, contradiction) + all traced adjustments."""
    from app.outcome.models import (
        CONFIDENCE_CEILING,
        CONFIDENCE_FLOOR,
        OUTCOME_BASE_CONFIDENCE,
        UNVERIFIABLE_CONTRADICTION_CONFIDENCE,
    )

    for scenario_type, payment_id in first_journey_ids.items():
        result = _decide(seeded, payment_id)
        if result.primary_reason.rule_id == "CRITICAL_CONTRADICTION":
            base = UNVERIFIABLE_CONTRADICTION_CONFIDENCE
        else:
            base = OUTCOME_BASE_CONFIDENCE[result.outcome]
        total_delta = round(
            sum(adjustment.delta for adjustment in result.confidence_adjustments), 2
        )
        expected = round(
            min(CONFIDENCE_CEILING, max(CONFIDENCE_FLOOR, base + total_delta)), 2
        )
        assert result.confidence == expected, scenario_type
        assert 0.05 <= result.confidence <= 0.99, scenario_type
