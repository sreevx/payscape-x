"""Tests for the Part 5 API endpoints.

Exercises GET /api/v1/outcome/{id} and the extended
GET /api/v1/analysis/{id} (which now includes the outcome) against a fully
seeded in-memory database, including 404 handling and deterministic output.
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
# /outcome/{transaction_id}
# ---------------------------------------------------------------------------

def test_outcome_endpoint_shape(client):
    transaction_id = _transaction_id(client, "normal_success")
    response = client.get(f"/api/v1/outcome/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("transaction_id", "outcome", "confidence", "primary_reason",
                "reasons", "supporting_evidence_ids", "supporting_event_ids",
                "blocking_evidence_ids", "consistency_status",
                "evidence_completeness", "rule_trace", "confidence_adjustments"):
        assert key in body, key
    assert body["transaction_id"] == transaction_id
    assert body["outcome"] == "FULFILLED"
    assert 0.05 <= body["confidence"] <= 0.99
    primary = body["primary_reason"]
    for key in ("code", "message", "severity", "rule_id", "event_ids", "evidence_ids"):
        assert key in primary, key
    assert body["reasons"]
    assert len(body["rule_trace"]) == 11  # every rule traced
    for step in body["rule_trace"]:
        assert step["applied"] in (True, False)
        assert step["note"]


def test_outcome_all_scenarios(client):
    expected = {
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
    for slug, outcome in expected.items():
        transaction_id = _transaction_id(client, slug)
        body = client.get(f"/api/v1/outcome/{transaction_id}").json()
        assert body["outcome"] == outcome, slug
        assert body["primary_reason"]["code"], slug


def test_outcome_traceability(client):
    transaction_id = _transaction_id(client, "compound_failure")
    journey = client.get(f"/api/v1/journeys/{transaction_id}").json()
    known_event_ids = {event["id"] for event in journey["events"]}
    evidence = client.get(f"/api/v1/evidence/{transaction_id}").json()
    known_evidence_ids = {item["evidence_id"] for item in evidence["evidence"]}
    body = client.get(f"/api/v1/outcome/{transaction_id}").json()
    for reason in body["reasons"]:
        for event_id in reason["event_ids"]:
            assert event_id in known_event_ids, reason["code"]
        for evidence_id in reason["evidence_ids"]:
            assert evidence_id in known_evidence_ids, reason["code"]
    for event_id in body["supporting_event_ids"]:
        assert event_id in known_event_ids
    for evidence_id in body["supporting_evidence_ids"] + body["blocking_evidence_ids"]:
        assert evidence_id in known_evidence_ids


def test_outcome_404(client):
    assert client.get("/api/v1/outcome/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/outcome/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_outcome_deterministic(client):
    transaction_id = _transaction_id(client, "contradictory_event")
    first = client.get(f"/api/v1/outcome/{transaction_id}").json()
    second = client.get(f"/api/v1/outcome/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# Extended /analysis/{transaction_id}
# ---------------------------------------------------------------------------

def test_analysis_includes_outcome(client):
    transaction_id = _transaction_id(client, "compound_failure")
    body = client.get(f"/api/v1/analysis/{transaction_id}").json()
    # Backward-compatible Part 4 fields all still present.
    for section in ("journey", "evidence", "consistency", "outcome"):
        assert section in body, section
    # Outcome matches the dedicated endpoint exactly.
    outcome = client.get(f"/api/v1/outcome/{transaction_id}").json()
    assert body["outcome"] == outcome
    # Part 4 responses unchanged.
    evidence = client.get(f"/api/v1/evidence/{transaction_id}").json()
    consistency = client.get(f"/api/v1/consistency/{transaction_id}").json()
    assert body["evidence"]["evidence"] == evidence["evidence"]
    assert body["consistency"]["checks"] == consistency["checks"]


def test_analysis_deterministic_with_outcome(client):
    transaction_id = _transaction_id(client, "normal_success")
    first = client.get(f"/api/v1/analysis/{transaction_id}").json()
    second = client.get(f"/api/v1/analysis/{transaction_id}").json()
    assert first == second
    assert first["outcome"]["outcome"] == "FULFILLED"


def test_analysis_404(client):
    assert client.get("/api/v1/analysis/not-a-uuid").status_code == 404


def test_all_scenarios_serve_outcome(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
        "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
        "contradictory_event", "compound_failure",
    ]
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        assert client.get(f"/api/v1/outcome/{transaction_id}").status_code == 200, slug
        analysis = client.get(f"/api/v1/analysis/{transaction_id}").json()
        assert analysis["outcome"]["outcome"], slug