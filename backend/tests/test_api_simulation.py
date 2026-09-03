"""Tests for the Part 7 Simulation Lab API endpoints.

Exercises GET /api/v1/simulations/{id}, POST /api/v1/simulations/{id}/run
and GET /api/v1/simulations/{id}/compare against a fully seeded in-memory
database (seed 42), including 404/400 handling, deterministic output and
read-only behaviour (no refund rows / events are ever created).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.main import create_app
from app.models import Refund, ScenarioInstance, TransactionEvent
from tests.seed_helpers import build_seeded_engine

ALL_INTERVENTION_TYPES = [
    "DO_NOTHING", "ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT",
    "SUBSTITUTE_PRODUCT", "REFUND", "HUMAN_REVIEW",
]


@pytest.fixture(scope="module")
def client():
    engine, factory = build_seeded_engine()
    app = create_app()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.factory = factory  # type: ignore[attr-defined]
        yield test_client
    engine.dispose()


def _transaction_id(client, scenario_slug: str, index: int = 0) -> str:
    body = client.get(
        f"/api/v1/transactions?scenario={scenario_slug}&limit=200"
    ).json()
    return body["items"][index]["id"]


# ---------------------------------------------------------------------------
# GET /simulations/{transaction_id}
# ---------------------------------------------------------------------------

def test_simulations_endpoint_shape(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.get(f"/api/v1/simulations/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"transaction_id", "baseline", "interventions", "comparison"}
    assert body["transaction_id"] == transaction_id
    baseline = body["baseline"]
    for key in ("outcome", "confidence", "severity", "impact_score",
                "compound_failure_detected", "root_causes", "event_ids",
                "evidence_ids"):
        assert key in baseline, key
    assert baseline["outcome"] == "FAILED"
    assert baseline["compound_failure_detected"] is True

    types = [item["intervention"]["intervention_type"]
             for item in body["interventions"]]
    assert types == ALL_INTERVENTION_TYPES
    for item in body["interventions"]:
        for key in ("simulation_id", "status", "reason", "baseline_outcome",
                    "simulated_outcome", "baseline_impact_score",
                    "simulated_impact_score", "delta_impact_score",
                    "resolved_failures", "remaining_failures", "new_risks",
                    "assumptions", "event_ids", "evidence_ids", "rule_ids",
                    "metadata"):
            assert key in item, key
    # Comparison is present and deterministic rows carry ranks.
    assert body["comparison"]
    ranks = [row["rank"] for row in body["comparison"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_simulations_all_scenarios_serve(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook",
        "delayed_webhook", "inventory_failure", "delivery_failure",
        "refund_flow", "missing_event", "contradictory_event",
        "compound_failure",
    ]
    expected_outcomes = {
        "normal_success": "FULFILLED",
        "payment_failed": "FAILED",
        "duplicate_webhook": "FULFILLED",
        "delayed_webhook": "FULFILLED",
        "inventory_failure": "FAILED",
        "delivery_failure": "FAILED",
        "refund_flow": "FAILED",
        "missing_event": "UNVERIFIABLE",
        "contradictory_event": "UNVERIFIABLE",
        "compound_failure": "FAILED",
    }
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        body = client.get(f"/api/v1/simulations/{transaction_id}").json()
        assert body["baseline"]["outcome"] == expected_outcomes[slug], slug
        assert len(body["interventions"]) == 6, slug
        statuses = {item["status"] for item in body["interventions"]}
        assert statuses <= {"SIMULATED", "NOT_APPLICABLE", "NOT_EFFECTIVE",
                            "NOT_SUPPORTED"}, slug


def test_simulations_404(client):
    assert client.get("/api/v1/simulations/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/simulations/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_simulations_deterministic(client):
    transaction_id = _transaction_id(client, "delivery_failure")
    first = client.get(f"/api/v1/simulations/{transaction_id}").json()
    second = client.get(f"/api/v1/simulations/{transaction_id}").json()
    assert first == second


def test_refund_is_marked_simulated(client):
    transaction_id = _transaction_id(client, "delivery_failure")
    body = client.get(f"/api/v1/simulations/{transaction_id}").json()
    refund = next(
        item for item in body["interventions"]
        if item["intervention"]["intervention_type"] == "REFUND"
    )
    assert refund["status"] == "SIMULATED"
    assert refund["metadata"]["labels"] == {"baseline": "ACTUAL",
                                            "simulated": "SIMULATED"}
    # Hypothetical refund events are deterministic and flagged, never real.
    assert refund["metadata"]["simulated_event_ids"]
    assert refund["simulated_outcome"] == "FAILED"


# ---------------------------------------------------------------------------
# POST /simulations/{transaction_id}/run
# ---------------------------------------------------------------------------

def test_run_single_intervention(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.post(
        f"/api/v1/simulations/{transaction_id}/run",
        json={"intervention": "DO_NOTHING"},
    )
    assert response.status_code == 200
    item = response.json()
    assert item["intervention"]["intervention_type"] == "DO_NOTHING"
    assert item["status"] == "SIMULATED"
    assert item["simulated_outcome"] == item["baseline_outcome"] == "FAILED"

    # The same single result appears inside the full report.
    full = client.get(f"/api/v1/simulations/{transaction_id}").json()
    matching = next(
        result for result in full["interventions"]
        if result["intervention"]["intervention_type"] == "DO_NOTHING"
    )
    assert matching == item


def test_run_unknown_intervention_400(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.post(
        f"/api/v1/simulations/{transaction_id}/run",
        json={"intervention": "SHIP_ROCKET"},
    )
    assert response.status_code == 400
    assert "SHIP_ROCKET" in response.json()["detail"]


def test_run_unknown_transaction_404(client):
    response = client.post(
        "/api/v1/simulations/00000000-0000-0000-0000-000000000000/run",
        json={"intervention": "REFUND"},
    )
    assert response.status_code == 404


def test_run_is_deterministic_and_read_only(client):
    transaction_id = _transaction_id(client, "inventory_failure")
    payment_uuid = uuid.UUID(transaction_id)
    with client.factory() as session:  # type: ignore[attr-defined]
        events_before = session.scalar(
            select(func.count()).select_from(TransactionEvent).where(
                TransactionEvent.payment_id == payment_uuid
            )
        )
        refunds_before = session.scalar(
            select(func.count()).select_from(Refund).where(
                Refund.payment_id == payment_uuid
            )
        )

    first = client.post(
        f"/api/v1/simulations/{transaction_id}/run",
        json={"intervention": "REFUND"},
    )
    second = client.post(
        f"/api/v1/simulations/{transaction_id}/run",
        json={"intervention": "REFUND"},
    )
    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "SIMULATED"

    with client.factory() as session:  # type: ignore[attr-defined]
        events_after = session.scalar(
            select(func.count()).select_from(TransactionEvent).where(
                TransactionEvent.payment_id == payment_uuid
            )
        )
        refunds_after = session.scalar(
            select(func.count()).select_from(Refund).where(
                Refund.payment_id == payment_uuid
            )
        )
    assert events_before == events_after
    assert refunds_before == refunds_after == 0


# ---------------------------------------------------------------------------
# GET /simulations/{transaction_id}/compare
# ---------------------------------------------------------------------------

def test_compare_endpoint(client):
    transaction_id = _transaction_id(client, "delivery_failure")
    compare = client.get(f"/api/v1/simulations/{transaction_id}/compare")
    assert compare.status_code == 200
    body = compare.json()
    assert body["comparison"]
    full = client.get(f"/api/v1/simulations/{transaction_id}").json()
    assert body["comparison"] == full["comparison"]
    assert body["interventions"] == full["interventions"]
    # Reference anchor is always present in the comparison.
    types = {row["intervention_type"] for row in body["comparison"]}
    assert "DO_NOTHING" in types


def test_compare_404(client):
    assert client.get(
        "/api/v1/simulations/00000000-0000-0000-0000-000000000000/compare"
    ).status_code == 404


def test_existing_analysis_endpoints_unchanged(client):
    """Part 1-6 endpoints remain intact alongside the lab."""
    transaction_id = _transaction_id(client, "compound_failure")
    for path in (f"/api/v1/journeys/{transaction_id}",
                 f"/api/v1/evidence/{transaction_id}",
                 f"/api/v1/consistency/{transaction_id}",
                 f"/api/v1/outcome/{transaction_id}",
                 f"/api/v1/failures/{transaction_id}",
                 f"/api/v1/impact/{transaction_id}",
                 f"/api/v1/analysis/{transaction_id}"):
        assert client.get(path).status_code == 200, path
