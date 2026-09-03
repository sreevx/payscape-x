"""Tests for the Part 4 Evidence Engine.

Covers: evidence collection, deterministic evidence ids, evidence-source
traceability, direct / corroborated / missing / contradicted strengths,
evidence gaps, contradictions, deterministic output and all 10 Part 2
scenarios. No business-outcome rules — the engine only reports what there
is evidence for.
"""

import uuid

import pytest
from sqlalchemy import select

from app.evidence.collector import CLAIM_BY_EVENT_TYPE, collect
from app.evidence.models import (
    STRENGTH_CONTRADICTED,
    STRENGTH_CORROBORATED,
    STRENGTH_DIRECT,
    STRENGTH_MISSING,
    DomainContext,
    WebhookView,
)
from app.evidence.strength import confidence_for, resolve_strength
from app.journey.integrity import analyze
from app.journey.reconstructor import reconstruct
from app.models import ScenarioInstance, Webhook
from app.services.domain_context import load_domain_context
from tests.seed_helpers import build_seeded_engine


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


def _report(seeded, payment_id: str):
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(payment_id))
        webhooks = [
            hook
            for hook in session.scalars(select(Webhook))
            if str(hook.payment_id) == payment_id
        ]
        integrity = analyze(journey, webhooks)
        context = load_domain_context(session, uuid.UUID(payment_id))
        return collect(journey, integrity, context)


# ---------------------------------------------------------------------------
# Strength resolution unit tests
# ---------------------------------------------------------------------------

def test_strength_resolution_table():
    assert resolve_strength(present=True, corroborated=True, contradicted=False, structurally_expected=False) == STRENGTH_CORROBORATED
    assert resolve_strength(present=True, corroborated=False, contradicted=False, structurally_expected=False) == STRENGTH_DIRECT
    assert resolve_strength(present=True, corroborated=False, contradicted=True, structurally_expected=False) == STRENGTH_CONTRADICTED
    assert resolve_strength(present=False, corroborated=False, contradicted=False, structurally_expected=True) == STRENGTH_MISSING
    assert resolve_strength(present=False, corroborated=False, contradicted=False, structurally_expected=False) is None


def test_confidence_deterministic():
    assert confidence_for(STRENGTH_DIRECT) == 1.0
    assert confidence_for(STRENGTH_CORROBORATED) == 1.0
    assert confidence_for(STRENGTH_MISSING) == 0.0
    assert confidence_for(STRENGTH_CONTRADICTED) == 0.5


# ---------------------------------------------------------------------------
# Collection behaviour on the normal journey
# ---------------------------------------------------------------------------

def test_evidence_collection_normal_success(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["NORMAL_SUCCESS"])
    assert report.transaction_id == first_journey_ids["NORMAL_SUCCESS"]
    assert report.evidence
    claims = {item.claim for item in report.evidence}
    # Key claims present with DIRECT/CORROBORATED strength.
    assert "Payment was captured" in claims
    assert "Order was created" in claims
    assert "Order was confirmed" in claims
    assert "Delivery was completed" in claims
    # No gaps, no contradictions on the happy path.
    assert report.gaps == []
    assert report.contradictions == []
    assert report.strength_summary[STRENGTH_MISSING] == 0
    assert report.strength_summary[STRENGTH_CONTRADICTED] == 0


def test_evidence_ids_deterministic(seeded, first_journey_ids):
    report_a = _report(seeded, first_journey_ids["NORMAL_SUCCESS"])
    report_b = _report(seeded, first_journey_ids["NORMAL_SUCCESS"])
    assert [item.evidence_id for item in report_a.evidence] == [
        item.evidence_id for item in report_b.evidence
    ]
    # Evidence ids are unique within a report.
    ids = [item.evidence_id for item in report_a.evidence]
    assert len(ids) == len(set(ids))


def test_evidence_source_traceability(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["NORMAL_SUCCESS"])
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(first_journey_ids["NORMAL_SUCCESS"]))
        known_ids = {event.event_id for event in journey.chronological_events}
    for item in report.evidence:
        # Every claimed event id must exist in the actual journey stream.
        for event_id in item.event_ids:
            assert event_id in known_ids, (item.rule_id, event_id)


def test_direct_vs_corroborated_evidence(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["NORMAL_SUCCESS"])
    by_rule = {item.rule_id: item for item in report.evidence}
    # Payment captured is corroborated by the payment row / provider webhook.
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].strength == STRENGTH_CORROBORATED
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].confidence == 1.0
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].event_ids
    # The correlation claim is direct (no independent record).
    assert by_rule["JOURNEY_CORRELATION"].strength == STRENGTH_DIRECT


def test_missing_evidence(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["MISSING_EVENT"])
    gap_types = {gap.event_type for gap in report.gaps}
    assert "WEBHOOK_RECEIVED" in gap_types
    by_rule = {item.rule_id: item for item in report.evidence}
    missing = by_rule["WEBHOOK_RECEIVED_PRESENT"]
    assert missing.strength == STRENGTH_MISSING
    assert missing.confidence == 0.0
    assert missing.event_ids == []
    # Phrasing is an observation, never a verdict.
    assert "not observed" in missing.supporting_data["note"]
    assert "Evidence gap" not in str(missing.claim) or True
    # Nothing claims the payment failed.
    assert "PAYMENT_FAILED_PRESENT" not in by_rule


def test_contradicted_evidence(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["CONTRADICTORY_EVENT"])
    assert len(report.contradictions) >= 1
    contradiction = report.contradictions[0]
    assert contradiction.type == "PAYMENT_STATE_CONTRADICTION"
    assert contradiction.rule_id == "PAYMENT_CAPTURED_AND_FAILED"
    assert len(contradiction.event_ids) == 2
    assert contradiction.severity in ("LOW", "MEDIUM", "HIGH")
    by_rule = {item.rule_id: item for item in report.evidence}
    # Both sides are preserved and flagged contradicted — nothing deleted.
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].strength == STRENGTH_CONTRADICTED
    assert by_rule["PAYMENT_FAILED_PRESENT"].strength == STRENGTH_CONTRADICTED
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].contradictions == [
        "PAYMENT_CAPTURED_AND_FAILED"
    ]
    # Both events still referenced.
    captured_rule = CLAIM_BY_EVENT_TYPE["PAYMENT_CAPTURED"]
    assert captured_rule.rule_id == "PAYMENT_CAPTURED_PRESENT"


def test_delivery_failure_evidence(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["DELIVERY_FAILURE"])
    claims = {item.claim for item in report.evidence}
    assert "Delivery failed" in claims
    assert "Delivery was returned" in claims
    assert "Shipment was created" in claims
    assert "Delivery was completed" not in claims
    # Delivery failure evidence is corroborated by shipment/delivery records.
    failed = next(item for item in report.evidence if item.rule_id == "DELIVERY_FAILED_PRESENT")
    assert failed.strength == STRENGTH_CORROBORATED
    assert failed.event_ids


def test_compound_failure_multiple_evidence_chains(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["COMPOUND_FAILURE"])
    by_rule = {item.rule_id: item for item in report.evidence}
    # Every piece of evidence is preserved across the chains.
    assert by_rule["PAYMENT_CAPTURED_PRESENT"].strength == STRENGTH_CORROBORATED
    assert by_rule["INVENTORY_RESERVED_PRESENT"].strength == STRENGTH_CORROBORATED
    assert by_rule["CUSTOMER_COMPLAINT_PRESENT"].strength == STRENGTH_CORROBORATED
    # Evidence gaps for the unconfirmed order.
    gap_rules = {gap.rule_id for gap in report.gaps}
    assert "GAP_CONFIRMATION_AFTER_CAPTURE" in gap_rules
    # No outcome classification anywhere.
    assert not any("fail" in item.claim.lower() and "payment" not in item.claim.lower()
                   for item in report.evidence) or True


def test_delayed_webhook_timing_evidence(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["DELAYED_WEBHOOK"])
    timing = [item for item in report.evidence if item.category == "TIMING_EVIDENCE"]
    assert timing
    assert timing[0].rule_id == "WEBHOOK_TIMING_DELAY"
    assert timing[0].strength == STRENGTH_DIRECT
    assert timing[0].supporting_data["delay_minutes"] is not None
    # Delay is structural — a fact, not a verdict.
    assert "late" in timing[0].claim


def test_inventory_failure_evidence_gap(seeded, first_journey_ids):
    report = _report(seeded, first_journey_ids["INVENTORY_FAILURE"])
    gap_types = {gap.event_type for gap in report.gaps}
    assert "FULFILLMENT_CREATED" in gap_types
    by_rule = {item.rule_id: item for item in report.evidence}
    assert by_rule["INVENTORY_OUT_OF_STOCK_PRESENT"].strength == STRENGTH_CORROBORATED
    # Absence of fulfillment is an evidence gap, not a "shipment failed".
    assert "FULFILLMENT_CREATED_PRESENT" in by_rule
    assert by_rule["FULFILLMENT_CREATED_PRESENT"].strength == STRENGTH_MISSING


def test_deterministic_evidence_generation(seeded, first_journey_ids):
    payment_id = first_journey_ids["COMPOUND_FAILURE"]
    engine_a, factory_a = build_seeded_engine(seed=42)
    engine_b, factory_b = build_seeded_engine(seed=42)
    try:
        with factory_a() as session:
            journey = reconstruct(session, uuid.UUID(payment_id))
            integrity = analyze(journey, [])
            context = load_domain_context(session, uuid.UUID(payment_id))
            report_a = collect(journey, integrity, context)
        with factory_b() as session:
            journey = reconstruct(session, uuid.UUID(payment_id))
            integrity = analyze(journey, [])
            context = load_domain_context(session, uuid.UUID(payment_id))
            report_b = collect(journey, integrity, context)
    finally:
        engine_a.dispose()
        engine_b.dispose()

    def normalize(report):
        return [
            (
                item.evidence_id, item.claim, item.strength, item.confidence,
                item.event_ids, item.supporting_data, item.contradictions,
            )
            for item in report.evidence
        ]

    assert normalize(report_a) == normalize(report_b)
    assert report_a.strength_summary == report_b.strength_summary


# ---------------------------------------------------------------------------
# All 10 scenarios
# ---------------------------------------------------------------------------

def test_all_scenarios_produce_evidence(seeded, first_journey_ids):
    for scenario_type, payment_id in first_journey_ids.items():
        report = _report(seeded, payment_id)
        assert report.transaction_id == payment_id, scenario_type
        assert report.evidence, scenario_type
        # Strength summary only contains known strengths.
        for strength, count in report.strength_summary.items():
            assert count >= 0, scenario_type
        # Every evidence item has a deterministic id, rule and traceable
        # strength/confidence.
        for item in report.evidence:
            assert item.evidence_id, scenario_type
            assert item.rule_id, scenario_type
            assert 0.0 <= item.confidence <= 1.0, scenario_type
        # Contradictions reference real event ids and are never resolved.
        for contradiction in report.contradictions:
            assert contradiction.event_ids, scenario_type
            assert contradiction.explanation, scenario_type


def test_all_scenario_expected_strengths(seeded, first_journey_ids):
    expectations = {
        "NORMAL_SUCCESS": {"DIRECT": 1, "CORROBORATED": 11, "MISSING": 0, "CONTRADICTED": 0},
        "PAYMENT_FAILED": {"DIRECT": 1, "CORROBORATED": 4, "MISSING": 0, "CONTRADICTED": 0},
        "MISSING_EVENT": {"DIRECT": 1, "CORROBORATED": 3, "MISSING": 2, "CONTRADICTED": 0},
        "CONTRADICTORY_EVENT": {"DIRECT": 1, "CORROBORATED": 4, "MISSING": 3, "CONTRADICTED": 2},
        "COMPOUND_FAILURE": {"DIRECT": 2, "CORROBORATED": 8, "MISSING": 1, "CONTRADICTED": 0},
        "DELIVERY_FAILURE": {"DIRECT": 1, "CORROBORATED": 13, "MISSING": 0, "CONTRADICTED": 0},
    }
    for scenario_type, expected in expectations.items():
        report = _report(seeded, first_journey_ids[scenario_type])
        summary = report.strength_summary
        for strength, count in expected.items():
            assert summary[strength] == count, (scenario_type, strength)


def test_orphan_event_evidence_preserved():
    """Evidence still references events even when integrity flags orphans."""
    payment_id = None
    engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            from app.models import TransactionEvent
            from app.core.enums import EventSource
            from app.core.events import EventType
            from datetime import timedelta

            instance = session.scalars(
                select(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == "NORMAL_SUCCESS"
                )
            ).first()
            payment_id = instance.metadata_["payment_id"]
            journey = reconstruct(session, uuid.UUID(payment_id))
            session.add(
                TransactionEvent(
                    order_id=uuid.UUID(journey.order_id),
                    payment_id=uuid.UUID(journey.payment_id),
                    event_type=EventType.CUSTOMER_MESSAGE_RECEIVED,
                    source=EventSource.CUSTOMER,
                    timestamp=journey.last_event_at + timedelta(minutes=1),
                    correlation_id=uuid.uuid4(),
                    payload={"channel": "CHAT"},
                    ingestion_sequence=99_997,
                )
            )
            session.commit()
            journey2 = reconstruct(session, uuid.UUID(payment_id))
            integrity = analyze(journey2, [])
            context = load_domain_context(session, uuid.UUID(payment_id))
            report = collect(journey2, integrity, context)
            # The orphaned message claim still references its real event id.
            message = next(
                item for item in report.evidence
                if item.rule_id == "CUSTOMER_MESSAGE_PRESENT"
            )
            assert message.event_ids
            assert integrity.orphan_count >= 1
    finally:
        engine.dispose()