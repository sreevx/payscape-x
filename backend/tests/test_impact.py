"""Tests for the Part 6 Consequence / Impact Engine.

Engine-level tests run the pure `analyze` without cross-transaction facts;
service-level tests exercise the cohort loader over the seeded dataset,
verifying the SHARED inventory condition across multiple transactions
(genuinely present in the seed-42 data on the zero-stock SKUs).
"""

import uuid

import pytest

from app.impact.engine import analyze as analyze_impact
from app.models import ScenarioInstance
from app.services import impact_service, journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.failures_service import build_failure
from app.services.outcome_service import build_outcome
from tests.seed_helpers import build_seeded_engine


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


def _run(factory, transaction_id: str, cross=None):
    with factory() as session:
        journey, integrity, _graph = journeys_service._reconstruct_all(
            session, transaction_id
        )
        context = load_domain_context(session, uuid.UUID(journey.payment_id))
        evidence = build_evidence(journey, integrity, context)
        consistency = build_consistency(journey, context)
        outcome = build_outcome(journey, integrity, evidence, consistency)
        failure = build_failure(journey, integrity, evidence, consistency, outcome)
        impact = analyze_impact(
            journey, integrity, evidence, consistency, outcome, failure, cross
        )
        known_event_ids = {event.event_id for event in journey.chronological_events}
        known_evidence_ids = {item.evidence_id for item in evidence.evidence}
        return {
            "impact": impact,
            "failure": failure,
            "outcome": outcome,
            "event_ids": known_event_ids,
            "evidence_ids": known_evidence_ids,
        }


# ---------------------------------------------------------------------------
# Consequences per scenario (engine level, no cross facts)
# ---------------------------------------------------------------------------

def test_non_failed_scenarios_report_no_consequences(session_factory):
    for slug in ("normal_success", "duplicate_webhook", "delayed_webhook",
                 "missing_event", "contradictory_event"):
        pipeline = _run(session_factory, _tx_id(session_factory, slug))
        impact = pipeline["impact"]
        assert impact.scope == "SINGLE_TRANSACTION"
        assert impact.observed_consequences == []
        assert impact.derived_consequences == []
        assert impact.potential_consequences == []
        assert impact.impact_score == 0.0
        assert impact.severity == "LOW"
        assert impact.affected_transactions == 0


def test_payment_failed_consequences(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "payment_failed"))
    impact = pipeline["impact"]
    # Observed facts only — no downstream consequences are invented.
    claims = {item.claim for item in impact.observed_consequences}
    assert any("Payment failed" in claim and "never captured" in claim for claim in claims)
    assert any("order was cancelled after the payment attempt failed" in claim for claim in claims)
    assert impact.derived_consequences == []
    assert impact.potential_consequences == []
    assert impact.affected_transactions == 1
    assert impact.severity == "MEDIUM"
    assert impact.impact_score > 0


def test_inventory_failure_consequences(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "inventory_failure"))
    impact = pipeline["impact"]
    observed = {item.claim for item in impact.observed_consequences}
    assert any("Inventory allocation failed" in claim for claim in observed)
    assert any("Fulfillment never created" in claim for claim in observed)
    derived = {item.claim for item in impact.derived_consequences}
    assert any("could not proceed" in claim for claim in derived)
    assert any("A shipment could not be created" in claim for claim in derived)
    assert any("delivery promise was not met" in claim for claim in derived)
    # No customer signal -> no potential consequences.
    assert impact.potential_consequences == []


def test_delivery_failure_consequences(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "delivery_failure"))
    impact = pipeline["impact"]
    observed = {item.claim for item in impact.observed_consequences}
    assert any("Delivery failed" in claim for claim in observed)
    assert any("returned to merchant" in claim for claim in observed)
    derived = {item.claim for item in impact.derived_consequences}
    assert any("customer did not receive" in claim for claim in derived)
    # Customer contacted support about the failure -> refund risk POTENTIAL.
    assert len(impact.potential_consequences) == 1
    assert impact.potential_consequences[0].classification == "POTENTIAL"
    assert "no refund has been recorded" in impact.potential_consequences[0].claim


def test_refund_flow_consequences(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "refund_flow"))
    impact = pipeline["impact"]
    observed = {item.claim for item in impact.observed_consequences}
    assert any("Order cancelled after capture" in claim for claim in observed)
    assert any("refund was initiated" in claim for claim in observed)
    assert any("refund was completed" in claim for claim in observed)
    derived = {item.claim for item in impact.derived_consequences}
    assert any("returned to the customer" in claim for claim in derived)
    # No complaint — no dispute-risk potential.
    assert impact.potential_consequences == []


def test_compound_failure_consequences(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "compound_failure"))
    impact = pipeline["impact"]
    observed = {item.claim for item in impact.observed_consequences}
    for expected in (
        "Provider webhook delayed",
        "Order never confirmed",
        "Inventory reservation expired",
        "Inventory allocation failed",
        "Fulfillment never created",
        "Customer impact recorded",
    ):
        assert any(expected in claim for claim in observed), expected
    potential = [item for item in impact.potential_consequences]
    assert len(potential) == 1
    assert potential[0].classification == "POTENTIAL"
    assert "Refund or dispute risk" in potential[0].claim
    assert impact.severity == "CRITICAL"


# ---------------------------------------------------------------------------
# Determinism + score methodology + traceability
# ---------------------------------------------------------------------------

def test_deterministic_impact(session_factory):
    for slug in ("compound_failure", "refund_flow", "delivery_failure"):
        transaction_id = _tx_id(session_factory, slug)
        first = _run(session_factory, transaction_id)
        second = _run(session_factory, transaction_id)
        assert first["impact"] == second["impact"], slug
        assert first["impact"].impact_id == str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"payscape:impact:{transaction_id}")
        ), slug


def test_impact_score_transparent_and_bounded(session_factory):
    for slug in ("compound_failure", "inventory_failure", "delivery_failure",
                 "refund_flow", "payment_failed"):
        impact = _run(session_factory, _tx_id(session_factory, slug))["impact"]
        assert 0.0 <= impact.impact_score <= 100.0, slug
        assert impact.score_components, slug
        assert impact.score_components[0].signal.startswith("SEVERITY_BASE_")
        total_components = round(
            sum(component.points for component in impact.score_components), 1
        )
        assert impact.impact_score == min(100.0, total_components), slug


def test_consequence_traceability(session_factory):
    pipeline = _run(session_factory, _tx_id(session_factory, "compound_failure"))
    impact = pipeline["impact"]
    for item in (
        impact.observed_consequences
        + impact.derived_consequences
        + impact.potential_consequences
    ):
        assert set(item.event_ids) <= pipeline["event_ids"]
        assert set(item.evidence_ids) <= pipeline["evidence_ids"]
        assert item.consequence_id == str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"payscape:consequence:{impact.transaction_id}:{item.rule_id}:{item.classification}",
            )
        )
    assert set(impact.event_ids) <= pipeline["event_ids"]
    assert set(impact.evidence_ids) <= pipeline["evidence_ids"]


def test_no_potential_without_customer_signal(session_factory):
    """POTENTIAL consequences only appear when a customer signalled."""
    pipeline = _run(session_factory, _tx_id(session_factory, "inventory_failure"))
    assert pipeline["impact"].potential_consequences == []


# ---------------------------------------------------------------------------
# Cross-transaction impact (service level — real cohort in seed 42)
# ---------------------------------------------------------------------------

def test_cross_transaction_scope_multi(session_factory):
    """The seed-42 dataset genuinely shares shortage SKUs across orders."""
    transaction_id = _tx_id(session_factory, "inventory_failure")
    with session_factory() as session:
        response = impact_service.get_impact(session, transaction_id)
    assert response.scope == "MULTI_TRANSACTION"
    assert response.affected_transactions >= 2
    assert response.affected_orders == response.affected_transactions
    assert response.shared_skus, "expected a shared shortage SKU"
    assert response.shared_failure_patterns == ["INVENTORY_OUT_OF_STOCK"]
    assert len(response.affected) == response.affected_transactions - 1
    for member in response.affected:
        assert member.transaction_id != transaction_id
        assert member.outcome == "FAILED"
        assert member.impact == "OBSERVED"
        assert member.scenario_slug in ("inventory_failure", "compound_failure")
        assert member.product_skus
        assert member.external_order_id


def test_single_transaction_scope_without_shared_sku(session_factory):
    transaction_id = _tx_id(session_factory, "delivery_failure")
    with session_factory() as session:
        response = impact_service.get_impact(session, transaction_id)
    assert response.scope == "SINGLE_TRANSACTION"
    assert response.affected_transactions == 1
    assert response.shared_skus == []
    assert response.affected == []


def test_multi_impact_raises_severity(session_factory):
    # Engine-level (no cross facts): HIGH. Service-level with the real
    # cohort: severity is raised because the shortage spans transactions.
    single = _run(session_factory, _tx_id(session_factory, "inventory_failure"))
    transaction_id = _tx_id(session_factory, "inventory_failure")
    with session_factory() as session:
        response = impact_service.get_impact(session, transaction_id)
    assert single["impact"].severity == "HIGH"
    assert response.severity == "CRITICAL"
    assert response.impact_score >= single["impact"].impact_score
    assert any(
        component.signal == "MULTI_TRANSACTION"
        for component in response.score_components
    )


def test_analysis_package_includes_part6(session_factory):
    """The analysis service composes journey + evidence + consistency +
    outcome + compound failure + impact deterministically."""
    from app.services.analysis_service import get_analysis

    transaction_id = _tx_id(session_factory, "compound_failure")
    with session_factory() as session:
        analysis = get_analysis(session, transaction_id)
    assert analysis is not None
    payload = analysis.model_dump()
    for key in ("journey", "evidence", "consistency", "outcome",
                "compound_failure", "impact"):
        assert key in payload, key
    assert payload["compound_failure"]["detected"] is True
    assert payload["impact"]["scope"] == "MULTI_TRANSACTION"
