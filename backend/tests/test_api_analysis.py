"""Tests for the Part 4 API endpoints.

Exercises GET /api/v1/evidence/{id}, GET /api/v1/consistency/{id} and
GET /api/v1/analysis/{id} against a fully seeded in-memory database,
including 404 handling and deterministic output.
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
# /evidence/{transaction_id}
# ---------------------------------------------------------------------------

def test_evidence_endpoint_shape(client):
    transaction_id = _transaction_id(client, "normal_success")
    response = client.get(f"/api/v1/evidence/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("transaction_id", "evidence", "gaps", "contradictions", "strength_summary"):
        assert key in body, key
    assert body["transaction_id"] == transaction_id
    assert body["evidence"]
    item = body["evidence"][0]
    for key in ("evidence_id", "category", "claim", "event_ids", "source",
                "timestamp", "supporting_data", "strength", "rule_id",
                "confidence", "contradictions"):
        assert key in item, key
    for strength in ("DIRECT", "CORROBORATED", "INDIRECT", "MISSING", "CONTRADICTED"):
        assert strength in body["strength_summary"], strength


def test_evidence_traceability(client):
    transaction_id = _transaction_id(client, "normal_success")
    journey = client.get(f"/api/v1/journeys/{transaction_id}").json()
    known_ids = {event["id"] for event in journey["events"]}
    evidence = client.get(f"/api/v1/evidence/{transaction_id}").json()
    for item in evidence["evidence"]:
        for event_id in item["event_ids"]:
            assert event_id in known_ids, (item["rule_id"], event_id)


def test_evidence_contradictory_scenario(client):
    transaction_id = _transaction_id(client, "contradictory_event")
    body = client.get(f"/api/v1/evidence/{transaction_id}").json()
    assert len(body["contradictions"]) >= 1
    contradiction = body["contradictions"][0]
    assert contradiction["contradiction_id"]
    assert contradiction["rule_id"] == "PAYMENT_CAPTURED_AND_FAILED"
    assert len(contradiction["event_ids"]) == 2
    contradicted = [
        item for item in body["evidence"] if item["strength"] == "CONTRADICTED"
    ]
    assert len(contradicted) >= 2


def test_evidence_endpoint_404(client):
    assert client.get("/api/v1/evidence/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/evidence/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_evidence_deterministic(client):
    transaction_id = _transaction_id(client, "compound_failure")
    first = client.get(f"/api/v1/evidence/{transaction_id}").json()
    second = client.get(f"/api/v1/evidence/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# /consistency/{transaction_id}
# ---------------------------------------------------------------------------

def test_consistency_endpoint_shape(client):
    transaction_id = _transaction_id(client, "normal_success")
    response = client.get(f"/api/v1/consistency/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("transaction_id", "checks", "passed", "violations",
                "insufficient_evidence", "not_applicable", "overall_integrity"):
        assert key in body, key
    assert body["overall_integrity"] == "CONSISTENT"
    check = body["checks"][0]
    for key in ("rule_id", "name", "description", "severity", "status",
                "supporting_event_ids", "explanation"):
        assert key in check, key
    assert check["status"] in (
        "PASS", "VIOLATION", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE",
    )
    # 16 rules evaluated.
    assert len(body["checks"]) == 16


def test_consistency_contradictory_inconsistent(client):
    transaction_id = _transaction_id(client, "contradictory_event")
    body = client.get(f"/api/v1/consistency/{transaction_id}").json()
    assert body["overall_integrity"] == "INCONSISTENT"
    assert "PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED" in body["violations"]


def test_consistency_insufficient_webhook(client):
    transaction_id = _transaction_id(client, "missing_event")
    body = client.get(f"/api/v1/consistency/{transaction_id}").json()
    assert "WEBHOOK_PAYMENT_REFERENCE_VALID" in body["insufficient_evidence"]
    # A missing webhook is never a violation.
    assert body["violations"] == []


def test_consistency_endpoint_404(client):
    assert client.get("/api/v1/consistency/nope").status_code == 404
    assert client.get(
        "/api/v1/consistency/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_consistency_deterministic(client):
    transaction_id = _transaction_id(client, "compound_failure")
    first = client.get(f"/api/v1/consistency/{transaction_id}").json()
    second = client.get(f"/api/v1/consistency/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# /analysis/{transaction_id}
# ---------------------------------------------------------------------------

def test_analysis_endpoint_package(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.get(f"/api/v1/analysis/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"] == transaction_id
    for section in ("journey", "evidence", "consistency"):
        assert section in body, section
    # Journey section matches the dedicated journey endpoint.
    journey = client.get(f"/api/v1/journeys/{transaction_id}").json()
    assert body["journey"]["events"] == journey["events"]
    assert body["journey"]["integrity"] == journey["integrity"]
    # Evidence section matches the dedicated evidence endpoint.
    evidence = client.get(f"/api/v1/evidence/{transaction_id}").json()
    assert body["evidence"]["evidence"] == evidence["evidence"]
    # Consistency section matches the dedicated consistency endpoint.
    consistency = client.get(f"/api/v1/consistency/{transaction_id}").json()
    assert body["consistency"]["checks"] == consistency["checks"]
    assert body["consistency"]["overall_integrity"] == consistency["overall_integrity"]


def test_analysis_endpoint_404(client):
    assert client.get("/api/v1/analysis/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/analysis/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_analysis_deterministic(client):
    transaction_id = _transaction_id(client, "normal_success")
    first = client.get(f"/api/v1/analysis/{transaction_id}").json()
    second = client.get(f"/api/v1/analysis/{transaction_id}").json()
    assert first == second


def test_all_scenarios_serve_200(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
        "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
        "contradictory_event", "compound_failure",
    ]
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        assert client.get(f"/api/v1/evidence/{transaction_id}").status_code == 200, slug
        assert client.get(
            f"/api/v1/consistency/{transaction_id}"
        ).status_code == 200, slug
        assert client.get(f"/api/v1/analysis/{transaction_id}").status_code == 200, slug