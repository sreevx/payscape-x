"""Journey reconstruction (Part 3).

Builds the canonical chronological journey for one transaction (payment)
from the unified TransactionEvent stream.

Reconstruction preserves the raw record exactly:
- chronological order is derived from event timestamps (never mutated)
- ingestion order is kept separately (best-available proxy: created_at then
  deterministic row id) so timestamp order != ingestion order is detectable
- duplicates, delays, contradictions, missing and unknown events are kept

Reconstruction describes what happened. It never repairs history and never
decides what should have happened.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment, TransactionEvent


@dataclass
class JourneyEvent:
    """One event of the reconstructed journey (view over a raw row)."""

    event_id: str
    order_id: Optional[str]
    payment_id: Optional[str]
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str
    idempotency_key: Optional[str]
    payload: dict
    # Position in the ingestion order (created_at, id) — NOT timestamp order.
    ingestion_position: int
    # Integrity flags (filled by journey.integrity.analyze).
    is_duplicate: bool = False
    is_unknown: bool = False
    is_orphan: bool = False
    duplicate_of_event_id: Optional[str] = None


@dataclass
class ReconstructedJourney:
    """A payment's canonical journey: events in both orderings + metadata."""

    transaction_id: str
    order_id: Optional[str]
    payment_id: str
    correlation_id: Optional[str]
    # Primary view: chronological (timestamp, id). Never the raw sort.
    chronological_events: list[JourneyEvent] = field(default_factory=list)
    # Secondary view: ingestion order (created_at, id).
    ingestion_events: list[JourneyEvent] = field(default_factory=list)

    @property
    def total_events(self) -> int:
        return len(self.chronological_events)

    @property
    def first_event_at(self) -> Optional[datetime]:
        if not self.chronological_events:
            return None
        return self.chronological_events[0].timestamp

    @property
    def last_event_at(self) -> Optional[datetime]:
        if not self.chronological_events:
            return None
        return self.chronological_events[-1].timestamp

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.first_event_at is None or self.last_event_at is None:
            return None
        return (self.last_event_at - self.first_event_at).total_seconds()


def reconstruct(
    session: Session, payment_id: uuid.UUID
) -> Optional[ReconstructedJourney]:
    """Reconstruct a payment's journey, or None when the payment is unknown."""
    payment = session.get(Payment, payment_id)
    if payment is None:
        return None

    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.payment_id == payment_id
            )
        )
    )

    # Ingestion order: the authoritative monotonic insertion sequence.
    # Timestamps are never used here — so out-of-order ingestion is visible.
    ingestion_sorted = sorted(rows, key=lambda row: row.ingestion_sequence)
    position_by_id = {
        str(row.id): index for index, row in enumerate(ingestion_sorted)
    }

    def to_journey_event(row: TransactionEvent, ingestion_position: int) -> JourneyEvent:
        return JourneyEvent(
            event_id=str(row.id),
            order_id=str(row.order_id),
            payment_id=str(row.payment_id) if row.payment_id else None,
            event_type=row.event_type.value,
            source=row.source.value,
            timestamp=row.timestamp,
            correlation_id=str(row.correlation_id),
            idempotency_key=row.idempotency_key,
            payload=dict(row.payload or {}),
            ingestion_position=ingestion_position,
        )

    events = [to_journey_event(row, position_by_id[str(row.id)]) for row in rows]
    chronological = sorted(events, key=lambda event: (event.timestamp, event.event_id))
    ingestion = sorted(events, key=lambda event: event.ingestion_position)

    # Primary correlation: the most common correlation among the journey's
    # events (deterministic tiebreak). Events carrying a different
    # correlation are preserved and reported as orphans — never merged.
    correlation_counts = Counter(event.correlation_id for event in events)
    primary_correlation = (
        max(correlation_counts.items(), key=lambda pair: (pair[1], pair[0]))[0]
        if correlation_counts
        else None
    )
    return ReconstructedJourney(
        transaction_id=str(payment.id),
        order_id=str(payment.order_id),
        payment_id=str(payment.id),
        correlation_id=primary_correlation,
        chronological_events=chronological,
        ingestion_events=ingestion,
    )