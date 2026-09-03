"""Tests for the Part 6 API endpoints.

Exercises GET /api/v1/failures/{id}, GET /api/v1/impact/{id}, the dataset
GET /api/v1/failures list and the extended GET /api/v1/analysis/{id}
against a fully seeded in-memory database (seed 42), including 404
handling, pagination and deterministic output.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from tests.seed_helpers import build_seeded_engine


@pytest.fixture(scope="module")
def client():
    """TestClient bound to a fully seeded in-memory database."""
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
        yield test_client
    engine.dispose()


def _transaction_id(client, scenario_slug: str, index: int = 0) -> str:
    body = client.get(
        f"/api/v1/transactions?scenario={scenario_slug}&limit=200"
    ).json()
    return body["items"][index]["id"]


# ---------------------------------------------------------------------------
# /failures/{transaction_id}
# ---------------------------------------------------------------------------

def test_failure_endpoint_shape(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.get(f"/api/v1/failures/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("compound_failure_id", "transaction_id", "detected", "reason",
                "severity", "classification", "primary_failure", "failure_chain",
                "edges", "root_causes", "confidence", "event_ids",
                "evidence_ids", "metadata"):
        assert key in body, key
    assert body["transaction_id"] == transaction_id
    assert body["detected"] is True
    assert body["severity"] == "CRITICAL"
    assert body["reason"] == "MULTI_STAGE_FAILURE_CHAIN"
    assert len(body["failure_chain"]) == 6
    assert body["primary_failure"]["kind"] == "INVENTORY_ALLOCATION_FAILED"
    # Traceability contract.
    journey = client.get(f"/api/v1/journeys/{transaction_id}").json()
    known_event_ids = {event["id"] for event in journey["events"]}
    for node in body["failure_chain"]:
        for event_id in node["event_ids"]:
            assert event_id in known_event_ids, node["kind"]
    for root in body["root_causes"]:
        for event_id in root["event_ids"]:
            assert event_id in known_event_ids


def test_failure_all_scenarios_serve(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
        "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
        "contradictory_event", "compound_failure",
    ]
    expected_detected = {
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
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        body = client.get(f"/api/v1/failures/{transaction_id}").json()
        assert body["detected"] is expected_detected[slug], slug
        # A FAILED but single-stage journey keeps severity MEDIUM.
        if slug in ("payment_failed", "refund_flow"):
            assert body["severity"] == "MEDIUM", slug


def test_failure_404(client):
    assert client.get("/api/v1/failures/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/failures/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_failure_deterministic(client):
    transaction_id = _transaction_id(client, "compound_failure")
    first = client.get(f"/api/v1/failures/{transaction_id}").json()
    second = client.get(f"/api/v1/failures/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# /impact/{transaction_id}
# ---------------------------------------------------------------------------

def test_impact_endpoint_shape(client):
    transaction_id = _transaction_id(client, "inventory_failure")
    response = client.get(f"/api/v1/impact/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("impact_id", "transaction_id", "scope", "affected_transactions",
                "affected_orders", "affected_products", "observed_consequences",
                "derived_consequences", "potential_consequences", "severity",
                "impact_score", "shared_skus", "shared_failure_patterns",
                "affected", "score_components", "event_ids", "evidence_ids",
                "metadata"):
        assert key in body, key
    assert body["scope"] == "MULTI_TRANSACTION"
    assert body["affected_transactions"] >= 2
    for member in body["affected"]:
        assert member["outcome"] == "FAILED"
        assert member["impact"] == "OBSERVED"


def test_impact_single_scope(client):
    transaction_id = _transaction_id(client, "delivery_failure")
    body = client.get(f"/api/v1/impact/{transaction_id}").json()
    assert body["scope"] == "SINGLE_TRANSACTION"
    assert body["affected_transactions"] == 1
    observed = {item["claim"] for item in body["observed_consequences"]}
    assert any("Delivery failed" in claim for claim in observed)
    potential = body["potential_consequences"]
    assert len(potential) == 1
    assert potential[0]["classification"] == "POTENTIAL"


def test_impact_404(client):
    assert client.get("/api/v1/impact/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/impact/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_impact_deterministic(client):
    transaction_id = _transaction_id(client, "compound_failure")
    first = client.get(f"/api/v1/impact/{transaction_id}").json()
    second = client.get(f"/api/v1/impact/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# /failures (dataset list)
# ---------------------------------------------------------------------------

def test_failures_list_totals_and_filters(client):
    body = client.get("/api/v1/failures?limit=100").json()
    # seed 42: 10 inventory + 10 delivery + 5 compound failures detected.
    assert body["total"] == 25
    assert len(body["items"]) == 25
    assert body["limit"] == 100
    for item in body["items"]:
        assert item["detected"] is True
        assert item["outcome"] == "FAILED"

    critical = client.get("/api/v1/failures?severity=CRITICAL&limit=100").json()
    assert critical["total"] == 5
    assert {item["severity"] for item in critical["items"]} == {"CRITICAL"}

    typed = client.get(
        "/api/v1/failures?failure_type=INVENTORY_ALLOCATION_FAILED&limit=100"
    ).json()
    assert typed["total"] == 15
    assert {item["primary_failure_kind"] for item in typed["items"]} == {
        "INVENTORY_ALLOCATION_FAILED"
    }

    failed = client.get("/api/v1/failures?outcome=FAILED&limit=100").json()
    assert failed["total"] == 25
    empty = client.get("/api/v1/failures?outcome=FULFILLED&limit=100").json()
    assert empty["total"] == 0


def test_failures_list_scope_filter(client):
    multi = client.get(
        "/api/v1/failures?scope=MULTI_TRANSACTION&limit=100"
    ).json()
    assert multi["total"] >= 10
    for item in multi["items"]:
        assert item["scope"] == "MULTI_TRANSACTION"
        assert item["affected_transactions"] >= 2
        assert item["shared_skus"]
    single = client.get(
        "/api/v1/failures?scope=SINGLE_TRANSACTION&limit=100"
    ).json()
    for item in single["items"]:
        assert item["scope"] == "SINGLE_TRANSACTION"
        assert item["shared_skus"] == []


def test_failures_list_pagination_and_determinism(client):
    page1 = client.get("/api/v1/failures?limit=5&offset=0").json()
    page2 = client.get("/api/v1/failures?limit=5&offset=5").json()
    assert len(page1["items"]) == 5
    assert len(page2["items"]) == 5
    first_ids = [item["transaction_id"] for item in page1["items"]]
    second_ids = [item["transaction_id"] for item in page2["items"]]
    assert not set(first_ids) & set(second_ids)
    # Deterministic across repeated calls.
    again = client.get("/api/v1/failures?limit=5&offset=0").json()
    assert page1 == again


# ---------------------------------------------------------------------------
# Extended /analysis/{transaction_id}
# ---------------------------------------------------------------------------

def test_analysis_includes_part6(client):
    transaction_id = _transaction_id(client, "compound_failure")
    body = client.get(f"/api/v1/analysis/{transaction_id}").json()
    # Backward-compatible sections all still present.
    for section in ("journey", "evidence", "consistency", "outcome",
                    "compound_failure", "impact"):
        assert section in body, section
    # Part 6 outputs match the dedicated endpoints.
    failure = client.get(f"/api/v1/failures/{transaction_id}").json()
    impact = client.get(f"/api/v1/impact/{transaction_id}").json()
    assert body["compound_failure"] == failure
    assert body["impact"] == impact
    # Part 4/5 outputs unchanged.
    evidence = client.get(f"/api/v1/evidence/{transaction_id}").json()
    consistency = client.get(f"/api/v1/consistency/{transaction_id}").json()
    outcome = client.get(f"/api/v1/outcome/{transaction_id}").json()
    assert body["evidence"]["evidence"] == evidence["evidence"]
    assert body["consistency"]["checks"] == consistency["checks"]
    assert body["outcome"] == outcome


def test_analysis_deterministic_with_part6(client):
    transaction_id = _transaction_id(client, "inventory_failure")
    first = client.get(f"/api/v1/analysis/{transaction_id}").json()
    second = client.get(f"/api/v1/analysis/{transaction_id}").json()
    assert first == second
    assert first["compound_failure"]["detected"] is True
    assert first["impact"]["scope"] == "MULTI_TRANSACTION"


def test_analysis_404(client):
    assert client.get("/api/v1/analysis/not-a-uuid").status_code == 404


def test_all_scenarios_serve_part6(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
        "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
        "contradictory_event", "compound_failure",
    ]
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        assert client.get(f"/api/v1/failures/{transaction_id}").status_code == 200, slug
        assert client.get(f"/api/v1/impact/{transaction_id}").status_code == 200, slug
        analysis = client.get(f"/api/v1/analysis/{transaction_id}").json()
        assert analysis["compound_failure"]["detected"] in (True, False), slug
        assert analysis["impact"]["impact_score"] >= 0, slug
