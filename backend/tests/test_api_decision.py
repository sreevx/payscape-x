"""Tests for the Part 8 Decision Agent API endpoints.

Exercises GET /api/v1/decisions/{transaction_id}, POST
/api/v1/decisions/{decision_id}/approve and POST
/api/v1/decisions/{decision_id}/reject against a fully seeded in-memory
database (seed 42), including:

- the deterministic fallback recommendation for all 10 scenarios
- the PENDING -> APPROVED / PENDING -> REJECTED lifecycle with 409 on
  invalid transitions and 404 on unknown ids
- approval-state preservation across regenerations
- read-only behaviour (approving never creates refunds or events)
- regression: every Parts 1-7 endpoint still serves
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.main import create_app
from app.models import Refund, TransactionEvent
from tests.seed_helpers import build_seeded_engine

# Deterministic expected recommendation per scenario (seed 42).
EXPECTED_ACTIONS = {
    "normal_success": "DO_NOTHING",
    "payment_failed": "DO_NOTHING",
    "duplicate_webhook": "DO_NOTHING",
    "delayed_webhook": "DO_NOTHING",
    "inventory_failure": "HUMAN_REVIEW",
    "delivery_failure": "REFUND_OR_CONTAIN",
    "refund_flow": "DO_NOTHING",
    "missing_event": "HUMAN_REVIEW",
    "contradictory_event": "HUMAN_REVIEW",
    "compound_failure": "REFUND_OR_CONTAIN",
}

DECISION_KEYS = {
    "decision_id", "transaction_id", "decision_source", "recommended_action",
    "reason", "decision_confidence", "evidence_confidence", "evidence_ids",
    "event_ids", "simulation_id", "alternatives", "human_approval_required",
    "approval_status", "rejection_reason", "decided_at", "created_at",
    "updated_at", "metadata",
}


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
# GET /decisions/{transaction_id}
# ---------------------------------------------------------------------------

def test_decision_endpoint_shape(client):
    transaction_id = _transaction_id(client, "compound_failure")
    response = client.get(f"/api/v1/decisions/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DECISION_KEYS
    assert body["transaction_id"] == transaction_id
    assert body["decision_source"] == "DETERMINISTIC_FALLBACK"
    assert body["recommended_action"] == "REFUND_OR_CONTAIN"
    assert body["approval_status"] == "PENDING"
    assert body["human_approval_required"] is True
    assert body["reason"]
    assert 0.0 <= body["decision_confidence"] <= 1.0
    # Fully traceable: references verified ids only.
    assert body["evidence_ids"]
    assert body["event_ids"]
    assert body["simulation_id"]
    assert len(body["alternatives"]) == 3
    # Recommendation is NOT an execution: metadata carries the labels.
    assert body["metadata"]["labels"]["approval"] == (
        "RECORDS APPROVAL ONLY — NEVER EXECUTES"
    )


def test_decision_all_scenarios(client):
    for slug, action in EXPECTED_ACTIONS.items():
        transaction_id = _transaction_id(client, slug)
        response = client.get(f"/api/v1/decisions/{transaction_id}")
        assert response.status_code == 200, slug
        body = response.json()
        assert body["recommended_action"] == action, slug
        assert body["decision_source"] == "DETERMINISTIC_FALLBACK", slug
        assert body["approval_status"] == "PENDING", slug
        assert body["metadata"]["fallback_rule_id"], slug
        assert body["human_approval_required"] == (action != "DO_NOTHING"), slug


def test_decision_deterministic(client):
    transaction_id = _transaction_id(client, "delivery_failure", index=2)
    first = client.get(f"/api/v1/decisions/{transaction_id}").json()
    second = client.get(f"/api/v1/decisions/{transaction_id}").json()
    for key in ("decision_id", "recommended_action", "reason",
                "decision_confidence", "evidence_ids", "event_ids",
                "simulation_id", "alternatives"):
        assert first[key] == second[key], key
    assert first["approval_status"] == "PENDING"


def test_decision_404(client):
    assert client.get("/api/v1/decisions/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/decisions/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_decision_no_refund_for_do_nothing(client):
    # normal_success / payment_failed recommend DO_NOTHING — no simulation
    # basis and no action execution.
    transaction_id = _transaction_id(client, "payment_failed")
    body = client.get(f"/api/v1/decisions/{transaction_id}").json()
    assert body["recommended_action"] == "DO_NOTHING"
    assert body["simulation_id"] is None


# ---------------------------------------------------------------------------
# Approval lifecycle
# ---------------------------------------------------------------------------

def test_approve_transition(client):
    transaction_id = _transaction_id(client, "inventory_failure")
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    assert client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["approval_status"] == "PENDING"

    response = client.post(
        f"/api/v1/decisions/{decision_id}/approve",
        json={"note": "merchant reviewed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "APPROVED"
    assert body["decision_id"] == decision_id
    assert body["decided_at"] is not None
    assert body["metadata"]["approval_note"] == "merchant reviewed"


def test_approve_again_conflict(client):
    transaction_id = _transaction_id(client, "inventory_failure", index=1)
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    assert client.post(
        f"/api/v1/decisions/{decision_id}/approve"
    ).status_code == 200
    response = client.post(f"/api/v1/decisions/{decision_id}/approve")
    assert response.status_code == 409
    assert "already" in response.json()["detail"]


def test_reject_transition_with_reason(client):
    transaction_id = _transaction_id(client, "missing_event")
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    response = client.post(
        f"/api/v1/decisions/{decision_id}/reject",
        json={"reason": "merchant disagrees with escalation"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "REJECTED"
    assert body["rejection_reason"] == "merchant disagrees with escalation"
    assert body["decided_at"] is not None


def test_reject_after_approve_conflict(client):
    transaction_id = _transaction_id(client, "contradictory_event", index=1)
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    assert client.post(
        f"/api/v1/decisions/{decision_id}/approve"
    ).status_code == 200
    response = client.post(
        f"/api/v1/decisions/{decision_id}/reject",
        json={"reason": "too late"},
    )
    assert response.status_code == 409


def test_approval_state_survives_regeneration(client):
    # GET after APPROVED must NOT reset the status to PENDING.
    transaction_id = _transaction_id(client, "delivery_failure", index=1)
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    assert client.post(
        f"/api/v1/decisions/{decision_id}/approve"
    ).status_code == 200
    refreshed = client.get(f"/api/v1/decisions/{transaction_id}").json()
    assert refreshed["approval_status"] == "APPROVED"
    assert refreshed["decision_id"] == decision_id


def test_approve_unknown_decision_404(client):
    response = client.post(
        "/api/v1/decisions/00000000-0000-0000-0000-000000000000/approve"
    )
    assert response.status_code == 404


def test_reject_unknown_decision_404(client):
    response = client.post(
        "/api/v1/decisions/00000000-0000-0000-0000-000000000000/reject",
        json={"reason": "x"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Read-only safety
# ---------------------------------------------------------------------------

def test_decisions_are_read_only(client):
    """Approving never creates refunds, events or payments."""
    transaction_id = _transaction_id(client, "delivery_failure", index=3)
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
    decision_id = client.get(
        f"/api/v1/decisions/{transaction_id}"
    ).json()["decision_id"]
    assert client.post(
        f"/api/v1/decisions/{decision_id}/approve"
    ).status_code == 200
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
# Regression
# ---------------------------------------------------------------------------

def test_existing_analysis_endpoints_unchanged(client):
    """Parts 1-7 endpoints remain intact alongside the decision API."""
    transaction_id = _transaction_id(client, "compound_failure")
    for path in (f"/api/v1/journeys/{transaction_id}",
                 f"/api/v1/evidence/{transaction_id}",
                 f"/api/v1/consistency/{transaction_id}",
                 f"/api/v1/outcome/{transaction_id}",
                 f"/api/v1/failures/{transaction_id}",
                 f"/api/v1/impact/{transaction_id}",
                 f"/api/v1/analysis/{transaction_id}",
                 f"/api/v1/simulations/{transaction_id}"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/v1/health").status_code == 200