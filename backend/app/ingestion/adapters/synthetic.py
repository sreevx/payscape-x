"""Synthetic-data adapter.

Translates an existing synthetic `TransactionEvent` row into a canonical
event. This is how the Part 2 dataset feeds the Part 3 pipeline unchanged:
the adapter carries over every field (including correlation and idempotency
identity) and records the original row reference.
"""

from typing import Any

from app.ingestion.adapters.base import EventAdapter
from app.ingestion.models import CanonicalEvent
from app.models import TransactionEvent


class SyntheticAdapter(EventAdapter):
    """Adapter for rows of the unified TransactionEvent stream."""

    def to_canonical(self, raw: Any) -> CanonicalEvent:
        if not isinstance(raw, TransactionEvent):
            raise ValueError(
                "SyntheticAdapter expects a TransactionEvent row, got "
                f"{type(raw).__name__}"
            )
        return CanonicalEvent(
            event_id=str(raw.id),
            event_type=raw.event_type.value,
            source=raw.source.value,
            timestamp=raw.timestamp,
            order_id=raw.order_id,
            payment_id=raw.payment_id,
            correlation_id=raw.correlation_id,
            idempotency_key=raw.idempotency_key,
            payload=dict(raw.payload or {}),
            original_event_reference={
                "kind": "synthetic",
                "table": "transaction_events",
                "id": str(raw.id),
            },
        )