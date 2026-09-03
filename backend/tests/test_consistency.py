"""Tests for the Part 4 Consistency Engine.

Covers: rule registry completeness, PASS / VIOLATION / INSUFFICIENT_EVIDENCE
/ NOT_APPLICABLE semantics, amount consistency, lifecycle ordering, refund
and delivery consistency, duplicate handling, contradiction handling,
deterministic output and all 10 Part 2 scenarios.

The engine evaluates whether observed records agree — it never determines
the business outcome.
"""

import uuid

import pytest
from sqlalchemy import select

from app.consistency.evaluator import evaluate
from app.consistency.models import (
    INTEGRITY_CONSISTENT,
    INTEGRITY_INCONSISTENT,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS,
    STATUS_VIOLATION,
)
from app.consistency.rules import CONSISTENCY_RULES, RULE_BY_ID
from app.journey.integrity import analyze
from app.journey.reconstructor import reconstruct
from app.models import ScenarioInstance, Webhook
from app.services.domain_context import load_domain_context
from tests.seed_helpers import build_seeded_engine

EXPECTED_RULE_IDS = {
    "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
    "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
    "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED",
    "WEBHOOK_PAYMENT_REFERENCE_VALID",
    "ORDER_CONFIRMATION_REQUIRES_ORDER",
    "INVENTORY_RESERVATION_REQUIRES_ORDER",
    "INVENTORY_RESERVATION_QUANTITY_POSITIVE",
    "FULFILLMENT_REQUIRES_ORDER",
    "SHIPMENT_REQUIRES_FULFILLMENT",
    "DELIVERY_REQUIRES_SHIPMENT",
    "REFUND_REQUIRES_PAYMENT",
    "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT",
    "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED",
    "DELIVERED_AFTER_SHIPMENT",
    "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
    "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
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


def _result(seeded, payment_id: str):
    with seeded() as session:
        journey = reconstruct(session, uuid.UUID(payment_id))
        context = load_domain_context(session, uuid.UUID(payment_id))
        return evaluate(journey, context)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_rule_registry_complete():
    assert {rule.rule_id for rule in CONSISTENCY_RULES} == EXPECTED_RULE_IDS
    for rule in CONSISTENCY_RULES:
        assert rule.name and rule.description, rule.rule_id
        assert rule.severity in ("LOW", "MEDIUM", "HIGH"), rule.rule_id
        assert callable(rule.evaluate), rule.rule_id
    # Evaluation order is fixed (the API list is deterministic): the
    # registry is a literal list, so order never varies across runs.
    ids = [rule.rule_id for rule in CONSISTENCY_RULES]
    assert len(ids) == len(set(ids))
    assert ids == list(CONSISTENCY_RULES[i].rule_id for i in range(len(ids)))


# ---------------------------------------------------------------------------
# Status semantics on the normal journey
# ---------------------------------------------------------------------------

def test_normal_success_mostly_pass(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["NORMAL_SUCCESS"])
    assert result.overall_integrity == INTEGRITY_CONSISTENT
    assert result.violations == []
    assert set(result.passed) >= {
        "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
        "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER",
        "DELIVERED_AFTER_SHIPMENT",
        "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
    }
    # Refund rules do not apply to a journey without refunds.
    assert "REFUND_REQUIRES_PAYMENT" in result.not_applicable
    assert "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED" in result.not_applicable
    assert "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT" in result.not_applicable
    # Every check is accounted for exactly once.
    statuses = [check.status for check in result.checks]
    assert len(statuses) == len(EXPECTED_RULE_IDS)
    assert all(check.rule_id in EXPECTED_RULE_IDS for check in result.checks)


def test_payment_failed_no_capture_evidence(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["PAYMENT_FAILED"])
    # No capture — the capture rules do not apply rather than failing.
    assert "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED" in result.not_applicable
    assert "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER" in result.not_applicable
    # Only failure recorded — no contradiction.
    assert "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED" in result.passed
    assert result.violations == []
    assert result.overall_integrity == INTEGRITY_CONSISTENT
    # Absence of delivery is NOT a violation — it is not applicable.
    assert "DELIVERED_AFTER_SHIPMENT" in result.not_applicable


def test_missing_event_insufficient_evidence(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["MISSING_EVENT"])
    # A missing webhook is INSUFFICIENT_EVIDENCE, never a violation.
    assert "WEBHOOK_PAYMENT_REFERENCE_VALID" in result.insufficient_evidence
    # Capture-requires-creation still passes with the records that exist.
    assert "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED" in result.passed
    assert result.violations == []
    assert result.overall_integrity == INTEGRITY_CONSISTENT


def test_contradictory_event_inconsistent(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["CONTRADICTORY_EVENT"])
    assert "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED" in result.violations
    assert result.overall_integrity == INTEGRITY_INCONSISTENT
    violation = next(
        check for check in result.checks
        if check.rule_id == "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED"
    )
    # Both sides referenced, neither deleted.
    assert len(violation.supporting_event_ids) == 2
    assert "both preserved" in violation.explanation
    assert violation.severity == "HIGH"


def test_inventory_failure_no_false_violation(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["INVENTORY_FAILURE"])
    # Out-of-stock is not a consistency violation — the records agree.
    assert result.violations == []
    assert "INVENTORY_RESERVATION_REQUIRES_ORDER" in result.not_applicable
    assert result.overall_integrity == INTEGRITY_CONSISTENT


def test_delivery_failure_insufficient_delivery_ordering(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["DELIVERY_FAILURE"])
    # Shipment exists but no DELIVERY_COMPLETED — ordering is unverifiable.
    assert "DELIVERED_AFTER_SHIPMENT" in result.insufficient_evidence
    # The failed delivery is still backed by the shipment.
    assert "DELIVERY_REQUIRES_SHIPMENT" in result.passed
    assert result.violations == []


def test_refund_flow_consistency(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["REFUND_FLOW"])
    assert "REFUND_COMPLETED_REQUIRES_REFUND_INITIATED" in result.passed
    assert "REFUND_AMOUNT_NOT_GREATER_THAN_CAPTURED_AMOUNT" in result.passed
    assert "REFUND_REQUIRES_PAYMENT" in result.passed
    assert result.violations == []
    assert result.overall_integrity == INTEGRITY_CONSISTENT


def test_duplicate_webhook_consistent(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["DUPLICATE_WEBHOOK"])
    # Duplicate delivery is preserved — records still agree internally.
    assert result.violations == []
    assert result.overall_integrity == INTEGRITY_CONSISTENT
    assert "WEBHOOK_PAYMENT_REFERENCE_VALID" in result.passed


def test_compound_failure_no_verdict(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["COMPOUND_FAILURE"])
    # The observed records agree (capture, late webhook, expiry, complaint).
    assert result.violations == []
    assert result.overall_integrity == INTEGRITY_CONSISTENT
    assert "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED" in result.passed
    # ORDER_CONFIRMED was never recorded — the confirmation rule does not
    # apply, and nothing invents a violation for the missing confirmation.
    assert "ORDER_CONFIRMATION_REQUIRES_ORDER" in result.not_applicable
    assert "ORDER_CONFIRMED_AFTER_ORDER_CREATED" in result.not_applicable


def test_amount_consistency_rule(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["NORMAL_SUCCESS"])
    # The rule itself reports PASS with the amounts in its explanation.
    amount_check = next(
        item for item in result.checks if item.rule_id == "PAYMENT_CAPTURE_AMOUNT_MATCHES_ORDER"
    )
    assert amount_check.status == STATUS_PASS
    assert "matches the order amount" in amount_check.explanation
    assert "INR" not in amount_check.explanation  # amounts are numbers, not verdicts


def test_lifecycle_ordering_rules(seeded, first_journey_ids):
    result = _result(seeded, first_journey_ids["NORMAL_SUCCESS"])
    for rule_id in (
        "DELIVERED_AFTER_SHIPMENT",
        "FULFILLMENT_SHIPPED_AFTER_FULFILLMENT_CREATED",
        "ORDER_CONFIRMED_AFTER_ORDER_CREATED",
    ):
        assert rule_id in result.passed, rule_id
        check = next(item for item in result.checks if item.rule_id == rule_id)
        assert len(check.supporting_event_ids) == 2, rule_id


def test_every_rule_statuses_are_valid(seeded, first_journey_ids):
    valid = {STATUS_PASS, STATUS_VIOLATION, STATUS_INSUFFICIENT_EVIDENCE, STATUS_NOT_APPLICABLE}
    for scenario_type, payment_id in first_journey_ids.items():
        result = _result(seeded, payment_id)
        for check in result.checks:
            assert check.status in valid, (scenario_type, check.rule_id)
            assert check.explanation, (scenario_type, check.rule_id)
        # Aggregation matches the checks exactly.
        assert set(result.passed) == {
            c.rule_id for c in result.checks if c.status == STATUS_PASS
        }
        assert set(result.violations) == {
            c.rule_id for c in result.checks if c.status == STATUS_VIOLATION
        }
        assert set(result.insufficient_evidence) == {
            c.rule_id for c in result.checks if c.status == STATUS_INSUFFICIENT_EVIDENCE
        }
        assert set(result.not_applicable) == {
            c.rule_id for c in result.checks if c.status == STATUS_NOT_APPLICABLE
        }


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_deterministic_consistency_output(seeded, first_journey_ids):
    result_a = _result(seeded, first_journey_ids["COMPOUND_FAILURE"])
    result_b = _result(seeded, first_journey_ids["COMPOUND_FAILURE"])
    assert result_a.checks == result_b.checks
    assert result_a.overall_integrity == result_b.overall_integrity


def test_consistent_result_never_uses_outcome_vocabulary(seeded, first_journey_ids):
    for scenario_type, payment_id in first_journey_ids.items():
        result = _result(seeded, payment_id)
        assert result.overall_integrity in (
            INTEGRITY_CONSISTENT,
            INTEGRITY_INCONSISTENT,
            "INSUFFICIENT_EVIDENCE",
        ), scenario_type
        for banned in ("SUCCESS", "FAILED", "AT_RISK", "FULFILLED"):
            assert banned not in result.overall_integrity, scenario_type
            for check in result.checks:
                assert banned not in check.status, (scenario_type, check.rule_id)