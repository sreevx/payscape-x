"""Ingestion service (Part 3).

Pipelines one raw event through: adapter → validate → normalize →
correlate → idempotency check → persist.

Contract guarantees:
- deterministic: same input + same database state → same outcome
- idempotent: re-ingesting an event with the same idempotency key returns a
  DUPLICATE result and writes nothing
- never silent: every input produces an explicit IngestionResult
  (PERSISTED / DUPLICATE / ORPHAN / UNKNOWN / REJECTED) with a message
- zero AI: no classification, no scoring, no autonomous decisions
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.adapters import EventAdapter, RawEventAdapter
from app.ingestion.models import CanonicalEvent, IngestionResult, IngestionStatus
from app.ingestion.normalizer import normalize_event
from app.ingestion.validator import validate_event
from app.journey.correlation import resolve_correlation
from app.models import Payment, TransactionEvent

logger = logging.getLogger(__name__)


class IngestionService:
    """Stateless ingestion pipeline; one instance per adapter."""

    def __init__(self, adapter: Optional[EventAdapter] = None):
        self.adapter = adapter or RawEventAdapter()

    # ------------------------------------------------------------------
    def ingest(self, session: Session, raw: Any) -> IngestionResult:
        """Ingest one raw event, returning an explicit result."""
        try:
            canonical = self.adapter.to_canonical(raw)
        except ValueError as exc:
            return IngestionResult(
                event=CanonicalEvent(
                    event_id="", event_type="", source="", timestamp=None,  # type: ignore[arg-type]
                    errors=[str(exc)],
                ),
                status=IngestionStatus.REJECTED,
                message=f"adapter could not interpret input: {exc}",
                errors=[str(exc)],
            )

        # 1. Structural validation.
        errors = validate_event(canonical)
        if errors:
            canonical.errors = errors
            canonical.ingestion_status = IngestionStatus.REJECTED
            return IngestionResult(
                event=canonical,
                status=IngestionStatus.REJECTED,
                message="event rejected: structural validation failed",
                errors=errors,
            )

        # 2. Deterministic normalization (single centralized registry).
        canonical = normalize_event(canonical)
        if canonical.is_unknown:
            return IngestionResult(
                event=canonical,
                status=IngestionStatus.UNKNOWN,
                message=(
                    "event type/source not in the registry — preserved and "
                    "marked UNKNOWN, not persisted"
                ),
            )

        # 3. Deterministic correlation (documented priority order).
        correlation, reason = resolve_correlation(session, canonical)
        canonical.correlation_id = correlation
        if correlation is None:
            canonical.ingestion_status = IngestionStatus.ORPHAN
            return IngestionResult(
                event=canonical,
                status=IngestionStatus.ORPHAN,
                message=(
                    "no deterministic correlation identity — event preserved "
                    "as an orphan, not persisted"
                ),
                correlation_reason=reason,
            )
        canonical.ingestion_status = IngestionStatus.CORRELATED
        _enrich_identities(session, canonical)

        # 4. Idempotency: one idempotency key per journey correlation.
        if canonical.idempotency_key:
            existing = session.scalars(
                select(TransactionEvent)
                .where(
                    TransactionEvent.idempotency_key == canonical.idempotency_key,
                    TransactionEvent.correlation_id == correlation,
                )
                .limit(1)
            ).first()
            if existing is not None:
                canonical.ingestion_status = IngestionStatus.DUPLICATE
                return IngestionResult(
                    event=canonical,
                    status=IngestionStatus.DUPLICATE,
                    message=(
                        f"duplicate: idempotency key "
                        f"{canonical.idempotency_key!r} already ingested"
                    ),
                    duplicate_of_event_id=str(existing.id),
                    correlation_reason=reason,
                )

        # 5. Persist into the unified stream.
        row = TransactionEvent(
            order_id=canonical.order_id,
            payment_id=canonical.payment_id,
            event_type=canonical.event_type,
            source=canonical.source,
            timestamp=canonical.timestamp,
            correlation_id=correlation,
            idempotency_key=canonical.idempotency_key,
            payload=canonical.payload,
            ingestion_sequence=_next_ingestion_sequence(session),
        )
        session.add(row)
        session.commit()
        canonical.ingestion_status = IngestionStatus.PERSISTED
        logger.info(
            "ingested %s (event_id=%s, correlation=%s, key=%s)",
            canonical.event_type,
            canonical.event_id,
            correlation,
            canonical.idempotency_key,
        )
        return IngestionResult(
            event=canonical,
            status=IngestionStatus.PERSISTED,
            message="event persisted to the unified stream",
            persisted_event_id=str(row.id),
            correlation_reason=reason,
        )


# ---------------------------------------------------------------------------
# Persist-time helpers
# ---------------------------------------------------------------------------

def _enrich_identities(session: Session, canonical: CanonicalEvent) -> None:
    """Backfill payment/order ids from deterministic domain relationships.

    The unified stream requires an order reference, so when correlation was
    resolved via payment id or provider_payment_id, the related order is
    attached from the existing payment row. Never guessed — always read from
    an existing domain record.
    """
    if canonical.payment_id is None:
        provider_payment_id = (canonical.payload or {}).get("provider_payment_id")
        if provider_payment_id:
            payment = session.scalars(
                select(Payment).where(
                    Payment.provider_payment_id == str(provider_payment_id)
                ).limit(1)
            ).first()
            if payment is not None:
                canonical.payment_id = payment.id
    if canonical.payment_id is not None and canonical.order_id is None:
        payment = session.get(Payment, canonical.payment_id)
        if payment is not None:
            canonical.order_id = payment.order_id


def _next_ingestion_sequence(session: Session) -> int:
    """Next monotonic ingestion sequence (max existing + 1)."""
    current = session.scalar(
        select(func.max(TransactionEvent.ingestion_sequence))
    )
    return int(current or 0) + 1