"""Tests for the Part 3 ingestion layer.

Covers: adapter extraction, deterministic normalization (including unknown
preservation), structural validation/rejection, idempotent ingestion,
correlation resolution priority and orphan preservation. No AI, no business
reasoning — the pipeline is deterministic.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.ingestion.adapters import RawEventAdapter, SyntheticAdapter
from app.ingestion.models import CanonicalEvent, IngestionStatus
from app.ingestion.normalizer import (
    normalize_event,
    normalize_event_type,
    normalize_source,
)
from app.ingestion.service import IngestionService
from app.ingestion.validator import validate_event
from app.models import ScenarioInstance, TransactionEvent
from tests.seed_helpers import build_seeded_engine


@pytest.fixture(scope="module")
def seeded():
    engine, factory = build_seeded_engine()
    yield factory
    engine.dispose()


@pytest.fixture(scope="module")
def journey(seeded):
    """A NORMAL_SUCCESS journey (payment + order + correlation)."""
    with seeded() as session:
        instance = session.scalars(
            select(ScenarioInstance)
            .where(ScenarioInstance.scenario_type == "NORMAL_SUCCESS")
            .limit(1)
        ).first()
        return {
            "payment_id": uuid.UUID(instance.metadata_["payment_id"]),
            "order_id": uuid.UUID(instance.metadata_["order_id"]),
            "correlation_id": instance.correlation_id,
        }


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _journey_session(seeded):
    return seeded()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_normalize_event_type_maps_provider_spellings():
    assert normalize_event_type("payment.captured") == ("PAYMENT_CAPTURED", False)
    assert normalize_event_type("payment_captured") == ("PAYMENT_CAPTURED", False)
    assert normalize_event_type("webhook.received") == ("WEBHOOK_RECEIVED", False)
    assert normalize_event_type("delivery.completed") == ("DELIVERY_COMPLETED", False)
    # Canonical identity passes through unchanged.
    assert normalize_event_type("ORDER_CONFIRMED") == ("ORDER_CONFIRMED", False)
    # Case-insensitive.
    assert normalize_event_type("PAYMENT.CAPTURED") == ("PAYMENT_CAPTURED", False)


def test_normalize_source_maps_provider_spellings():
    assert normalize_source("razorpay") == ("PAYMENT_PROVIDER", False)
    assert normalize_source("WEBHOOK") == ("WEBHOOK", False)
    assert normalize_source("customer") == ("CUSTOMER", False)
    assert normalize_source("PAYMENT_PROVIDER") == ("PAYMENT_PROVIDER", False)


def test_normalize_unknown_event_type_preserved():
    canonical, unknown = normalize_event_type("payment.cryptocurrency")
    assert unknown is True
    assert canonical == "payment.cryptocurrency"  # preserved, not remapped


def test_normalize_event_marks_unknown_and_preserves_raw():
    event = CanonicalEvent(
        event_id="evt-1",
        event_type="payment.cryptocurrency",
        source="razorpay",
        timestamp=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
    )
    normalize_event(event)
    assert event.is_unknown is True
    assert event.ingestion_status == IngestionStatus.UNKNOWN
    # The raw spelling survives inside the canonical event.
    assert event.event_type == "payment.cryptocurrency"
    assert event.source == "PAYMENT_PROVIDER"  # known source still normalized


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def test_synthetic_adapter_preserves_every_field(seeded, journey):
    with seeded() as session:
        row = session.scalars(
            select(TransactionEvent)
            .where(TransactionEvent.payment_id == journey["payment_id"])
            .order_by(TransactionEvent.timestamp)
            .limit(1)
        ).first()
        canonical = SyntheticAdapter().to_canonical(row)
        assert canonical.event_id == str(row.id)
        assert canonical.event_type == row.event_type.value
        assert canonical.source == row.source.value
        assert canonical.timestamp == row.timestamp
        assert canonical.order_id == row.order_id
        assert canonical.payment_id == row.payment_id
        assert canonical.correlation_id == row.correlation_id
        assert canonical.idempotency_key == row.idempotency_key
        assert canonical.payload == row.payload
        assert canonical.original_event_reference["table"] == "transaction_events"
        assert canonical.original_event_reference["id"] == str(row.id)


def test_raw_adapter_accepts_dict_and_preserves_payload(journey):
    payload = {"provider_payment_id": "pay_abc", "amount": "1999"}
    raw = {
        "event_id": "evt_raw_1",
        "event_type": "payment.captured",
        "source": "razorpay",
        "timestamp": "2026-08-24T10:05:00+00:00",
        "order_id": str(journey["order_id"]),
        "payment_id": str(journey["payment_id"]),
        "idempotency_key": "idem-raw-1",
        "payload": payload,
    }
    canonical = RawEventAdapter().to_canonical(raw)
    assert canonical.event_id == "evt_raw_1"
    assert canonical.event_type == "payment.captured"
    assert canonical.order_id == journey["order_id"]
    assert canonical.payload == payload  # original payload untouched


def test_raw_adapter_rejects_non_dict():
    with pytest.raises(ValueError):
        RawEventAdapter().to_canonical(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_event_accepts_well_formed(journey):
    event = CanonicalEvent(
        event_id="evt-1",
        event_type="PAYMENT_CAPTURED",
        source="PAYMENT_PROVIDER",
        timestamp=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
        order_id=journey["order_id"],
        payment_id=journey["payment_id"],
        payload={},
    )
    assert validate_event(event) == []


def test_validate_event_rejects_malformed(journey):
    base = dict(
        event_id="evt-bad",
        event_type="PAYMENT_CAPTURED",
        source="PAYMENT_PROVIDER",
        timestamp=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
        order_id=journey["order_id"],
        payload={},
    )
    # Missing event type.
    errors = validate_event(CanonicalEvent(**{**base, "event_type": ""}))
    assert any("event_type" in error for error in errors)
    # Missing timestamp.
    errors = validate_event(CanonicalEvent(**{**base, "timestamp": None}))  # type: ignore[arg-type]
    assert any("timestamp" in error for error in errors)
    # No correlatable identity at all.
    errors = validate_event(
        CanonicalEvent(
            event_id="evt-bad",
            event_type="PAYMENT_CAPTURED",
            source="PAYMENT_PROVIDER",
            timestamp=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
            order_id=None,
            payment_id=None,
            correlation_id=None,
            payload={},
        )
    )
    assert any("identity" in error for error in errors)
    # Payload must be an object.
    errors = validate_event(CanonicalEvent(**{**base, "payload": [1, 2]}))  # type: ignore[arg-type]
    assert any("payload" in error for error in errors)


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

def test_valid_event_ingestion_persists(seeded, journey):
    with seeded() as session:
        before = session.scalar(
            select(func.count())
            .select_from(TransactionEvent)
            .where(TransactionEvent.payment_id == journey["payment_id"])
        )
        service = IngestionService()
        result = service.ingest(
            session,
            {
                "event_id": "evt_ingest_1",
                "event_type": "payment.refunded",
                "source": "razorpay",
                "timestamp": _iso(datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)),
                "order_id": str(journey["order_id"]),
                "payment_id": str(journey["payment_id"]),
                "idempotency_key": f"idem-ingest-{uuid.uuid4()}",
                "payload": {"amount": "1999"},
            },
        )
        assert result.status == IngestionStatus.PERSISTED
        assert result.persisted_event_id is not None
        after = session.scalar(
            select(func.count())
            .select_from(TransactionEvent)
            .where(TransactionEvent.payment_id == journey["payment_id"])
        )
        assert after == before + 1
        # Stored in canonical registry vocabulary.
        row = session.get(TransactionEvent, uuid.UUID(result.persisted_event_id))
        assert row.event_type.value == "PAYMENT_REFUNDED"
        assert row.source.value == "PAYMENT_PROVIDER"
        assert row.correlation_id == journey["correlation_id"]


def test_malformed_event_rejected_nothing_persisted(seeded, journey):
    with seeded() as session:
        before = session.scalar(select(func.count()).select_from(TransactionEvent))
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_bad",
                "event_type": "",
                "source": "razorpay",
                "timestamp": _iso(datetime(2026, 9, 20, tzinfo=timezone.utc)),
                "order_id": str(journey["order_id"]),
            },
        )
        assert result.status == IngestionStatus.REJECTED
        assert result.errors
        after = session.scalar(select(func.count()).select_from(TransactionEvent))
        assert after == before


def test_idempotent_ingestion(seeded, journey):
    with seeded() as session:
        key = f"idem-same-{uuid.uuid4()}"
        raw = {
            "event_id": "evt_idem",
            "event_type": "webhook.received",
            "source": "webhook",
            "timestamp": _iso(datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)),
            "order_id": str(journey["order_id"]),
            "payment_id": str(journey["payment_id"]),
            "idempotency_key": key,
            "payload": {"provider_event_id": "evt_provider_1"},
        }
        before = session.scalar(select(func.count()).select_from(TransactionEvent))
        first = IngestionService().ingest(session, raw)
        assert first.status == IngestionStatus.PERSISTED
        second = IngestionService().ingest(session, raw)
        assert second.status == IngestionStatus.DUPLICATE
        assert second.duplicate_of_event_id == first.persisted_event_id
        after = session.scalar(select(func.count()).select_from(TransactionEvent))
        assert after == before + 1  # exactly one row persisted


def test_correlation_by_explicit_id_wins(journey):
    engine, factory = build_seeded_engine()
    explicit = uuid.uuid4()
    with factory() as session:
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_corr_explicit",
                "event_type": "ORDER_CONFIRMED",
                "source": "order_service",
                "timestamp": _iso(datetime(2026, 9, 22, tzinfo=timezone.utc)),
                "order_id": str(journey["order_id"]),
                "correlation_id": str(explicit),
                "payload": {},
            },
        )
        assert result.status == IngestionStatus.PERSISTED
        assert result.event.correlation_id == explicit
        assert result.correlation_reason == "explicit_correlation_id"
    engine.dispose()


def test_correlation_by_order_id(seeded, journey):
    with seeded() as session:
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_corr_order",
                "event_type": "ORDER_CREATED",
                "source": "order_service",
                "timestamp": _iso(datetime(2026, 9, 22, 1, tzinfo=timezone.utc)),
                "order_id": str(journey["order_id"]),
                "payload": {},
            },
        )
        assert result.status == IngestionStatus.PERSISTED
        assert result.event.correlation_id == journey["correlation_id"]
        assert result.correlation_reason == "order_id"


def test_correlation_by_payment_id(seeded, journey):
    with seeded() as session:
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_corr_payment",
                "event_type": "PAYMENT_CAPTURED",
                "source": "payment_provider",
                "timestamp": _iso(datetime(2026, 9, 22, 2, tzinfo=timezone.utc)),
                "payment_id": str(journey["payment_id"]),
                "payload": {},
            },
        )
        assert result.status == IngestionStatus.PERSISTED
        assert result.event.correlation_id == journey["correlation_id"]
        assert result.correlation_reason == "payment_id"


def test_correlation_by_provider_payment_id(seeded, journey):
    # Correlate purely from the payload's provider_payment_id — no order or
    # payment id on the event itself.
    from app.models import Payment

    with seeded() as session:
        payment = session.get(Payment, journey["payment_id"])
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_corr_provider",
                "event_type": "payment.failed",
                "source": "razorpay",
                "timestamp": _iso(datetime(2026, 9, 22, 3, tzinfo=timezone.utc)),
                "payload": {"provider_payment_id": payment.provider_payment_id},
            },
        )
        assert result.status == IngestionStatus.PERSISTED
        assert result.event.correlation_id == journey["correlation_id"]
        assert result.correlation_reason == "provider_payment_id"


def test_orphan_event_preserved_not_persisted(seeded):
    with seeded() as session:
        before = session.scalar(select(func.count()).select_from(TransactionEvent))
        # Valid structurally (provider identity present) but the provider id
        # matches no existing payment — correlation cannot be established.
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_orphan_1",
                "event_type": "webhook.received",
                "source": "webhook",
                "timestamp": _iso(datetime(2026, 9, 23, tzinfo=timezone.utc)),
                "payload": {"provider_payment_id": "pay_does_not_exist"},
            },
        )
        assert result.status == IngestionStatus.ORPHAN
        assert result.event.event_id == "evt_orphan_1"  # preserved
        assert result.correlation_reason is None
        after = session.scalar(select(func.count()).select_from(TransactionEvent))
        assert after == before  # never guessed a correlation, never persisted


def test_unknown_event_preserved_not_persisted(seeded, journey):
    with seeded() as session:
        before = session.scalar(select(func.count()).select_from(TransactionEvent))
        result = IngestionService().ingest(
            session,
            {
                "event_id": "evt_unknown_1",
                "event_type": "payment.cryptocurrency",
                "source": "razorpay",
                "timestamp": _iso(datetime(2026, 9, 23, 1, tzinfo=timezone.utc)),
                "order_id": str(journey["order_id"]),
                "payment_id": str(journey["payment_id"]),
                "payload": {},
            },
        )
        assert result.status == IngestionStatus.UNKNOWN
        assert result.event.event_type == "payment.cryptocurrency"  # preserved
        assert result.event.is_unknown is True
        after = session.scalar(select(func.count()).select_from(TransactionEvent))
        assert after == before