"""Tests for the Part 6 Compound Failure Engine.

Exercises detection, chain construction, root-cause selection, severity,
classification and traceability against all 10 synthetic scenarios on the
deterministic seeded dataset (seed 42). Every assertion is deterministic.
"""

import uuid

import pytest

from app.core.database import Base
from app.failures.engine import analyze as analyze_failure
from app.models import ScenarioInstance
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.outcome_service import build_outcome
from tests.seed_helpers import build_seeded_engine

NAMESPACE = uuid.NAMESPACE_URL


@pytest.fixture(scope="module")
def session_factory():
    _engine, factory = build_seeded_engine()
    yield factory
    _engine.dispose()


def _tx_id(factory, slug: str) -> str:
    from app.synthetic.scenarios import definition_for

    definition = definition_for(slug)
    with factory() as session:
        instance = session.query(ScenarioInstance).filter(
            ScenarioInstance.scenario_type == definition.scenario_type
        ).first()
        return str(uuid.UUID(instance.metadata_["payment_id"]))


def _pipeline(factory, transaction_id: str):
    with factory() as session:
        journey, integrity, _graph = journeys_service._reconstruct_all(
            session, transaction_id
        )
        context = load_domain_context(session, uuid.UUID(journey.payment_id))
        evidence = build_evidence(journey, integrity, context)
        consistency = build_consistency(journey, context)
        outcome = build_outcome(journey, integrity, evidence, consistency)
        failure = analyze_failure(journey, integrity, evidence, consistency, outcome)
        known_event_ids = {event.event_id for event in journey.chronological_events}
        known_evidence_ids = {item.evidence_id for item in evidence.evidence}
        return {
            "journey": journey,
            "outcome": outcome,
            "failure": failure,
            "event_ids": known_event_ids,
            "evidence_ids": known_evidence_ids,
        }


# ---------------------------------------------------------------------------
# Detection matrix — all 10 scenarios
# ---------------------------------------------------------------------------

DETECTION_EXPECTATIONS = {
    "normal_success": False,
    "payment_failed": False,
    "duplicate_webhook": False,
    "delayed_webhook": False,
    "inventory_failure": True,
    "delivery_failure": True,
    "refund_flow": False,
    "missing_event": False,
    "contradictory_event": False,
    "compound_failure": True,
}


def test_detection_matrix(session_factory):
    for slug, detected in DETECTION_EXPECTATIONS.items():
        transaction_id = _tx_id(session_factory, slug)
        pipeline = _pipeline(session_factory, transaction_id)
        assert pipeline["failure"].detected is detected, slug
        assert pipeline["failure"].transaction_id == transaction_id
        assert pipeline["failure"].compound_failure_id == str(
            uuid.uuid5(
                NAMESPACE, f"payscape:compound:{transaction_id}"
            )
        ), slug


def test_compound_failure_chain_shape(session_factory):
    transaction_id = _tx_id(session_factory, "compound_failure")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]

    kinds = [node.kind for node in failure.failure_chain]
    assert kinds == [
        "WEBHOOK_DELAYED",
        "ORDER_NOT_CONFIRMED",
        "INVENTORY_RESERVATION_EXPIRED",
        "INVENTORY_ALLOCATION_FAILED",
        "FULFILLMENT_NOT_CREATED",
        "CUSTOMER_IMPACT",
    ]
    # Every chain node is a recorded event (nothing derived/invented here).
    assert all(node.status == "OBSERVED" for node in failure.failure_chain)
    assert failure.classification == "OBSERVED"
    assert failure.severity == "CRITICAL"
    assert failure.reason == "MULTI_STAGE_FAILURE_CHAIN"
    assert len(failure.edges) == len(failure.failure_chain) - 1
    assert [edge.relationship_type for edge in failure.edges] == [
        "LEADS_TO", "LEADS_TO", "LEADS_TO", "BLOCKS", "IMPACTS",
    ]
    assert "WEBHOOK_DELAY_LEADS_TO_ORDER_FAILURE" in {
        edge.rule_id for edge in failure.edges
    }
    assert "INVENTORY_FAILURE_BLOCKS_FULFILLMENT" in {
        edge.rule_id for edge in failure.edges
    }
    assert "DELIVERY_FAILURE_IMPACTS_CUSTOMER" not in {
        edge.rule_id for edge in failure.edges
    }


def test_inventory_failure_chain(session_factory):
    transaction_id = _tx_id(session_factory, "inventory_failure")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]
    assert failure.detected is True
    kinds = [node.kind for node in failure.failure_chain]
    assert kinds == ["INVENTORY_ALLOCATION_FAILED", "FULFILLMENT_NOT_CREATED"]
    assert len(failure.edges) == 1
    assert failure.edges[0].relationship_type == "BLOCKS"
    assert failure.edges[0].rule_id == "INVENTORY_FAILURE_BLOCKS_FULFILLMENT"
    assert failure.severity == "HIGH"


def test_delivery_failure_chain(session_factory):
    transaction_id = _tx_id(session_factory, "delivery_failure")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]
    assert failure.detected is True
    kinds = [node.kind for node in failure.failure_chain]
    assert kinds == ["DELIVERY_FAILED", "DELIVERY_RETURNED", "CUSTOMER_IMPACT"]
    assert [edge.relationship_type for edge in failure.edges] == [
        "LEADS_TO", "IMPACTS",
    ]
    assert failure.severity == "HIGH"


def test_single_stage_failures_not_compound(session_factory):
    # A lone payment failure is a single-stage business failure — the
    # engine must not dress it up as a compound chain.
    transaction_id = _tx_id(session_factory, "payment_failed")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]
    assert failure.detected is False
    assert failure.reason == "SINGLE_STAGE_BUSINESS_FAILURE"
    assert failure.severity == "MEDIUM"
    assert [node.kind for node in failure.failure_chain] == ["PAYMENT_FAILED"]
    assert failure.edges == []
    # The post-failure order cancellation is NOT an independent chain node.
    assert "ORDER_CANCELLED_AFTER_CAPTURE" not in {
        node.kind for node in failure.failure_chain
    }


def test_refund_flow_single_stage(session_factory):
    transaction_id = _tx_id(session_factory, "refund_flow")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]
    assert failure.detected is False
    assert failure.severity == "MEDIUM"
    assert [node.kind for node in failure.failure_chain] == [
        "ORDER_CANCELLED_AFTER_CAPTURE",
    ]


def test_non_failed_outcomes_report_no_chain(session_factory):
    normal = _pipeline(session_factory, _tx_id(session_factory, "normal_success"))
    assert normal["failure"].detected is False
    assert normal["failure"].severity == "LOW"
    assert normal["failure"].reason == "NO_FAILURE_OUTCOME_FULFILLED"

    missing = _pipeline(session_factory, _tx_id(session_factory, "missing_event"))
    assert missing["failure"].detected is False
    assert missing["failure"].reason == "OUTCOME_UNVERIFIABLE_NO_CHAIN"

    contradictory = _pipeline(
        session_factory, _tx_id(session_factory, "contradictory_event")
    )
    assert contradictory["failure"].detected is False
    assert contradictory["failure"].reason == "OUTCOME_UNVERIFIABLE_NO_CHAIN"

    duplicate = _pipeline(session_factory, _tx_id(session_factory, "duplicate_webhook"))
    assert duplicate["failure"].detected is False
    # A duplicate webhook alone is never a compound failure.
    assert duplicate["failure"].reason == "NO_FAILURE_OUTCOME_FULFILLED"


# ---------------------------------------------------------------------------
# Root-cause selection
# ---------------------------------------------------------------------------

def test_root_cause_compound_is_inventory_allocation(session_factory):
    transaction_id = _tx_id(session_factory, "compound_failure")
    pipeline = _pipeline(session_factory, transaction_id)
    failure = pipeline["failure"]
    assert len(failure.root_causes) == 1
    root = failure.root_causes[0]
    assert root.kind == "INVENTORY_ALLOCATION_FAILED"
    assert root.stage == "INVENTORY"
    assert root.rule_id == "ROOT_CAUSE_PRIORITY_SELECTION"
    assert root.root_cause_id == str(
        uuid.uuid5(NAMESPACE, f"payscape:root-cause:{transaction_id}:INVENTORY_ALLOCATION_FAILED")
    )
    assert "not the earliest event" not in root.explanation  # sanity
    # The primary failure points at the root node.
    assert failure.primary_failure is not None
    assert failure.primary_failure.kind == "INVENTORY_ALLOCATION_FAILED"


def test_root_cause_respects_priority_not_earliest(session_factory):
    """The webhook delay is EARLIEST in the chain but must never displace
    the business-stage root cause."""
    transaction_id = _tx_id(session_factory, "compound_failure")
    pipeline = _pipeline(session_factory, transaction_id)
    chain = pipeline["failure"].failure_chain
    assert chain[0].kind == "WEBHOOK_DELAYED"          # earliest observed
    assert pipeline["failure"].root_causes[0].kind == "INVENTORY_ALLOCATION_FAILED"


def test_root_cause_other_scenarios(session_factory):
    delivery = _pipeline(session_factory, _tx_id(session_factory, "delivery_failure"))
    assert delivery["failure"].root_causes[0].kind == "DELIVERY_FAILED"

    inventory = _pipeline(
        session_factory, _tx_id(session_factory, "inventory_failure")
    )
    assert inventory["failure"].root_causes[0].kind == "INVENTORY_ALLOCATION_FAILED"

    refund = _pipeline(session_factory, _tx_id(session_factory, "refund_flow"))
    assert refund["failure"].root_causes[0].kind == "ORDER_CANCELLED_AFTER_CAPTURE"


# ---------------------------------------------------------------------------
# Traceability + determinism
# ---------------------------------------------------------------------------

def test_chain_traceability(session_factory):
    for slug in ("compound_failure", "delivery_failure", "inventory_failure"):
        pipeline = _pipeline(session_factory, _tx_id(session_factory, slug))
        failure = pipeline["failure"]
        for node in failure.failure_chain:
            assert set(node.event_ids) <= pipeline["event_ids"], slug
            assert set(node.evidence_ids) <= pipeline["evidence_ids"], slug
        for edge in failure.edges:
            source = next(
                node for node in failure.failure_chain
                if node.node_id == edge.source_node
            )
            target = next(
                node for node in failure.failure_chain
                if node.node_id == edge.target_node
            )
            assert source is not None and target is not None
        for root in failure.root_causes:
            assert set(root.event_ids) <= pipeline["event_ids"], slug
            assert set(root.evidence_ids) <= pipeline["evidence_ids"], slug


def test_deterministic_repeated_execution(session_factory):
    for slug in ("compound_failure", "normal_success", "refund_flow"):
        transaction_id = _tx_id(session_factory, slug)
        first = _pipeline(session_factory, transaction_id)
        second = _pipeline(session_factory, transaction_id)
        assert first["failure"] == second["failure"], slug
        # uuid5 ids are stable across processes too (deterministic string).
        assert first["failure"].compound_failure_id == str(
            uuid.uuid5(NAMESPACE, f"payscape:compound:{transaction_id}")
        )


def test_outcome_integration(session_factory):
    """The failure engine consumes the Part 5 outcome, never recomputes it."""
    pipeline = _pipeline(session_factory, _tx_id(session_factory, "compound_failure"))
    assert pipeline["failure"].metadata["outcome"] == "FAILED"
    assert pipeline["failure"].metadata["outcome_reason_code"] in {
        "ORDER_NOT_CONFIRMED",
        "NO_FULFILLMENT",
        "INVENTORY_ALLOCATION_FAILED",
    }
    assert pipeline["failure"].metadata["distinct_stages"] == sorted(
        {"WEBHOOK", "ORDER", "INVENTORY", "FULFILLMENT", "CUSTOMER"}
    )
    assert pipeline["failure"].confidence == pipeline["outcome"].confidence
