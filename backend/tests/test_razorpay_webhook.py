"""Tests for Part 9 — Razorpay TEST-MODE webhook ingestion.

Covers: HMAC signature verification (valid / invalid / missing), the
RazorpayWebhookAdapter translation into canonical events, refund event
normalization, explicit payment correlation, idempotent redelivery,
orphan preservation for unknown payments, demo-mode bypass labelling, and
the safety boundary (ingestion + approval never perform financial actions).

The webhook endpoint passes every delivery through the SAME Part 3
pipeline as the synthetic dataset; these tests assert that contract.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.ingestion.adapters.razorpay import RazorpayWebhookAdapter
from app.ingestion.normalizer import normalize_event_type
from app.ingestion.razorpay import (
    extract_event_id,
    extract_event_timestamp,
    extract_provider_payment_id,
    parse_event_body,
    verify_signature,
)
from app.main import create_app
from app.models import Payment, Refund, ScenarioInstance, TransactionEvent, Webhook
from tests.seed_helpers import build_seeded_engine

TEST_SECRET = "test_webhook_secret_42"


class _FakeSettingsSecret:
    razorpay_webhook_secret = TEST_SECRET
    demo_mode = True


class _FakeSettingsNoSecret:
    razorpay_webhook_secret = ""
    demo_mode = True


def _sign(body: bytes, secret: str = TEST_SECRET) -> str:
    return base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")


def _webhook_event(
    payment_id: str,
    event: str = "payment.captured",
    *,
    entity_id: str | None = None,
    include_top_id: bool = True,
    created_at: int | None = None,
) -> dict:
    event_id = f"evt_{uuid.uuid4().hex[:20]}"
    payload_entity = {"id": entity_id or payment_id, "status": "captured"}
    if event.startswith("refund"):
        payload_entity = {
            "id": f"rfd_{uuid.uuid4().hex[:12]}",
            "payment_id": payment_id,
            "status": "processed",
        }
        wrapped = {"refund": {"entity": payload_entity}}
    else:
        wrapped = {"payment": {"entity": payload_entity}}
    payload: dict = {
        "entity": "event",
        "account_id": "acc_test_123",
        "event": event,
        "contains": ["payment"],
        "payload": wrapped,
        "created_at": created_at
        or int(datetime.now(timezone.utc).timestamp()),
    }
    if include_top_id:
        payload["id"] = event_id
    return payload


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


def _payment(client, index: int = 0):
    """A seeded Razorpay payment (provider_payment_id + journey correlation)."""
    with client.factory() as session:  # type: ignore[attr-defined]
        payment = session.scalars(select(Payment).offset(index).limit(1)).first()
        return {
            "provider_payment_id": payment.provider_payment_id,
            "id": str(payment.id),
        }


# ---------------------------------------------------------------------------
# Signature verification (unit)
# ---------------------------------------------------------------------------

def test_signature_verifies_valid_hmac():
    body = b'{"event": "payment.captured"}'
    assert verify_signature(body, _sign(body), TEST_SECRET) is True


def test_signature_rejects_tampered_body():
    body = b'{"event": "payment.captured"}'
    tampered = b'{"event": "payment.failed"}'
    assert verify_signature(tampered, _sign(body), TEST_SECRET) is False


def test_signature_rejects_missing_or_short():
    body = b'{"event": "payment.captured"}'
    assert verify_signature(body, None, TEST_SECRET) is False
    assert verify_signature(body, "", TEST_SECRET) is False
    assert verify_signature(body, "not-base64!", TEST_SECRET) is False


def test_signature_never_accepts_without_secret():
    body = b'{"event": "payment.captured"}'
    assert verify_signature(body, _sign(body, TEST_SECRET), "") is False


def test_parse_event_body_helpers():
    event = _webhook_event("pay_abc")
    body = json.dumps(event).encode()
    parsed = parse_event_body(body)
    assert parsed["event"] == "payment.captured"
    assert extract_provider_payment_id(parsed) == "pay_abc"
    assert extract_event_id(parsed) == event["id"]
    assert isinstance(extract_event_timestamp(parsed), datetime)


def test_parse_event_body_rejects_malformed():
    from app.ingestion.razorpay import RazorpayWebhookError

    with pytest.raises(RazorpayWebhookError) as exc:
        parse_event_body(b"not json{")
    assert exc.value.status == 400
    with pytest.raises(RazorpayWebhookError):
        parse_event_body(b"[]")


# ---------------------------------------------------------------------------
# Adapter + normalization
# ---------------------------------------------------------------------------

def test_adapter_produces_payment_and_webhook_events():
    event = _webhook_event("pay_abc", include_top_id=True)
    events = RazorpayWebhookAdapter().to_canonical_events(event)
    types = [(e.event_type, e.source) for e in events]
    assert types == [
        ("payment.captured", "razorpay"),
        ("webhook.received", "webhook"),
    ]
    payment_event, webhook_event = events
    assert payment_event.idempotency_key == (
        f"razorpay:payment.captured:{event['id']}"
    )
    assert webhook_event.idempotency_key == f"razorpay_webhook:{event['id']}"
    # The original provider payload is preserved untouched.
    assert payment_event.payload["raw"]["event"] == "payment.captured"
    assert payment_event.payload["provider_payment_id"] == "pay_abc"
    assert webhook_event.original_event_reference["kind"] == (
        "razorpay_webhook_delivery"
    )


def test_adapter_unknown_event_preserved_not_dropped():
    event = _webhook_event("pay_abc", event="payment.cryptocurrency")
    events = RazorpayWebhookAdapter().to_canonical_events(event)
    assert events[0].event_type == "payment.cryptocurrency"
    assert events[0].original_event_reference["kind"] == (
        "razorpay_webhook_unknown"
    )
    assert normalize_event_type("payment.cryptocurrency")[1] is True


def test_refund_aliases_normalize_to_registry():
    assert normalize_event_type("refund.created") == ("REFUND_INITIATED", False)
    assert normalize_event_type("refund.processed") == ("REFUND_COMPLETED", False)
    assert normalize_event_type("refund.failed") == ("REFUND_FAILED", False)


# ---------------------------------------------------------------------------
# API — signature enforcement
# ---------------------------------------------------------------------------

@pytest.fixture()
def with_secret(monkeypatch):
    monkeypatch.setattr(
        "app.services.razorpay_webhook_service.get_settings",
        lambda: _FakeSettingsSecret(),
    )


@pytest.fixture()
def without_secret(monkeypatch):
    monkeypatch.setattr(
        "app.services.razorpay_webhook_service.get_settings",
        lambda: _FakeSettingsNoSecret(),
    )


def test_valid_signature_accepted_and_persisted(client, with_secret):
    payment = _payment(client)
    body = json.dumps(_webhook_event(payment["provider_payment_id"])).encode()
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body)},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "razorpay_test_mode"
    assert result["signature_verified"] is True
    assert result["event"] == "payment.captured"
    assert result["provider_payment_id"] == payment["provider_payment_id"]
    assert result["webhook_processing_status"] == "PROCESSED"
    assert result["webhook_row_id"]

    statuses = {item["event_type"]: item["status"] for item in result["ingestion"]}
    assert statuses["PAYMENT_CAPTURED"] == "PERSISTED"
    assert statuses["WEBHOOK_RECEIVED"] == "PERSISTED"
    assert result["correlation_id"]

    # The events joined the payment's existing journey correlation.
    with client.factory() as session:  # type: ignore[attr-defined]
        persisted = session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.idempotency_key
                == f"razorpay_webhook:{result['event_id']}"
            )
        ).first()
        assert persisted is not None
        assert persisted.correlation_id is not None
        assert persisted.source.value == "WEBHOOK"
        webhook_row = session.get(Webhook, uuid.UUID(result["webhook_row_id"]))
        assert webhook_row.signature_verified is True
        assert webhook_row.provider == "razorpay"


def test_invalid_signature_rejected(client, with_secret):
    payment = _payment(client)
    body = json.dumps(_webhook_event(payment["provider_payment_id"])).encode()
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "invalid-signature"},
    )
    assert response.status_code == 400
    assert "Invalid" in response.json()["detail"]


def test_missing_signature_rejected(client, with_secret):
    payment = _payment(client)
    body = json.dumps(_webhook_event(payment["provider_payment_id"])).encode()
    response = client.post("/api/v1/webhooks/razorpay", content=body)
    assert response.status_code == 400
    assert "Missing" in response.json()["detail"]


def test_no_secret_no_bypass_rejected(client, without_secret):
    payment = _payment(client)
    body = json.dumps(_webhook_event(payment["provider_payment_id"])).encode()
    response = client.post("/api/v1/webhooks/razorpay", content=body)
    assert response.status_code == 400
    assert "secret not configured" in response.json()["detail"]


def test_demo_bypass_explicitly_unverified(client, without_secret):
    payment = _payment(client)
    body = json.dumps(_webhook_event(payment["provider_payment_id"])).encode()
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-PAYSCAPE-DEMO": "1"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "demo"
    assert result["signature_verified"] is False
    assert result["webhook_processing_status"] == "PROCESSED"
    assert [i["status"] for i in result["ingestion"]] == [
        "PERSISTED", "PERSISTED",
    ]


def test_malformed_body_rejected(client, with_secret):
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=b"this is not json",
        headers={"X-Razorpay-Signature": _sign(b"this is not json")},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# API — idempotency, correlation, orphan
# ---------------------------------------------------------------------------

def test_duplicate_redelivery_creates_no_duplicate_events(client, with_secret):
    payment = _payment(client, index=1)
    event = _webhook_event(payment["provider_payment_id"])
    body = json.dumps(event).encode()
    headers = {"X-Razorpay-Signature": _sign(body)}

    first = client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
    assert first.status_code == 200
    assert [i["status"] for i in first.json()["ingestion"]] == [
        "PERSISTED", "PERSISTED",
    ]

    with client.factory() as session:  # type: ignore[attr-defined]
        webhook_events_before = session.scalar(
            select(func.count()).select_from(TransactionEvent).where(
                TransactionEvent.idempotency_key
                == f"razorpay_webhook:{event['id']}"
            )
        )

    second = client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
    assert second.status_code == 200
    result = second.json()
    assert [i["status"] for i in result["ingestion"]] == [
        "DUPLICATE", "DUPLICATE",
    ]
    assert result["webhook_processing_status"] == "DUPLICATE"

    with client.factory() as session:  # type: ignore[attr-defined]
        webhook_events_after = session.scalar(
            select(func.count()).select_from(TransactionEvent).where(
                TransactionEvent.idempotency_key
                == f"razorpay_webhook:{event['id']}"
            )
        )
        webhook_rows = session.scalars(
            select(Webhook).where(Webhook.provider_event_id == event["id"])
        ).all()
    assert webhook_events_before == webhook_events_after == 1
    assert [row.processing_status.value for row in webhook_rows] == [
        "PROCESSED", "DUPLICATE",
    ]


def test_refund_webhook_normalized_and_correlated(client, with_secret):
    payment = _payment(client, index=2)
    event = _webhook_event(payment["provider_payment_id"], event="refund.processed")
    body = json.dumps(event).encode()
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body)},
    )
    assert response.status_code == 200
    result = response.json()
    statuses = {item["event_type"]: item["status"] for item in result["ingestion"]}
    assert statuses["REFUND_COMPLETED"] == "PERSISTED"
    assert statuses["WEBHOOK_RECEIVED"] == "PERSISTED"
    # Explicit provider identifier -> the payment's existing journey.
    assert result["correlation_id"]
    with client.factory() as session:  # type: ignore[attr-defined]
        payment_row = session.scalars(
            select(Payment).where(
                Payment.provider_payment_id == payment["provider_payment_id"]
            )
        ).first()
        event_row = session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == "REFUND_COMPLETED",
                TransactionEvent.payment_id == payment_row.id,
            )
        ).first()
        assert event_row is not None
        # The webhook event joined the payment's EXISTING journey
        # correlation (explicit provider identifier, never fuzzy).
        existing = session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.payment_id == payment_row.id,
                TransactionEvent.event_type == "PAYMENT_CAPTURED",
            )
        ).first()
        assert existing is not None
        assert event_row.correlation_id == existing.correlation_id


def test_unknown_payment_preserved_as_orphan(client, with_secret):
    event = _webhook_event("pay_does_not_exist_000")
    body = json.dumps(event).encode()
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body)},
    )
    assert response.status_code == 200
    result = response.json()
    assert [i["status"] for i in result["ingestion"]] == ["ORPHAN", "ORPHAN"]
    assert result["webhook_row_id"] is None
    assert result["correlation_id"] is None
    assert "ORPHAN" in result["message"]
    with client.factory() as session:  # type: ignore[attr-defined]
        webhook_rows = session.scalars(
            select(Webhook).where(Webhook.provider_event_id == event["id"])
        ).all()
        events = session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.idempotency_key
                == f"razorpay_webhook:{event['id']}"
            )
        ).all()
    assert webhook_rows == []
    assert events == []


# ---------------------------------------------------------------------------
# Safety boundary
# ---------------------------------------------------------------------------

def test_webhook_ingestion_is_read_only_on_domain_tables(client, with_secret):
    payment = _payment(client, index=3)
    event = _webhook_event(payment["provider_payment_id"])
    body = json.dumps(event).encode()
    with client.factory() as session:  # type: ignore[attr-defined]
        payment_row = session.scalars(
            select(Payment).where(
                Payment.provider_payment_id == payment["provider_payment_id"]
            )
        ).first()
        refunds_before = session.scalar(
            select(func.count()).select_from(Refund).where(
                Refund.payment_id == payment_row.id
            )
        )
        status_before = payment_row.status.value

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body)},
    )
    assert response.status_code == 200

    with client.factory() as session:  # type: ignore[attr-defined]
        payment_row = session.scalars(
            select(Payment).where(
                Payment.provider_payment_id == payment["provider_payment_id"]
            )
        ).first()
        refunds_after = session.scalar(
            select(func.count()).select_from(Refund).where(
                Refund.payment_id == payment_row.id
            )
        )
    assert refunds_before == refunds_after == 0
    assert payment_row.status.value == status_before


def test_approval_never_executes_financial_action(client, with_secret):
    """Part 8 approval + Part 9 ingestion both stop at the record level."""
    with client.factory() as session:  # type: ignore[attr-defined]
        instance = session.scalars(
            select(ScenarioInstance)
            .where(ScenarioInstance.scenario_type == "COMPOUND_FAILURE")
            .limit(1)
        ).first()
        payment_id = uuid.UUID(instance.metadata_["payment_id"])

    decision = client.get(f"/api/v1/decisions/{payment_id}")
    assert decision.status_code == 200
    decision_id = decision.json()["decision_id"]
    approved = client.post(f"/api/v1/decisions/{decision_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "APPROVED"

    with client.factory() as session:  # type: ignore[attr-defined]
        refunds = session.scalar(
            select(func.count()).select_from(Refund).where(
                Refund.payment_id == payment_id
            )
        )
    assert refunds == 0


def test_existing_analysis_endpoints_unchanged(client, with_secret):
    """Parts 1-8 endpoints remain intact alongside the webhook route."""
    with client.factory() as session:  # type: ignore[attr-defined]
        instance = session.scalars(
            select(ScenarioInstance)
            .where(ScenarioInstance.scenario_type == "COMPOUND_FAILURE")
            .limit(1)
        ).first()
        payment_id = instance.metadata_["payment_id"]
    for path in (f"/api/v1/journeys/{payment_id}",
                 f"/api/v1/evidence/{payment_id}",
                 f"/api/v1/consistency/{payment_id}",
                 f"/api/v1/outcome/{payment_id}",
                 f"/api/v1/failures/{payment_id}",
                 f"/api/v1/impact/{payment_id}",
                 f"/api/v1/simulations/{payment_id}",
                 f"/api/v1/analysis/{payment_id}"):
        assert client.get(path).status_code == 200, path