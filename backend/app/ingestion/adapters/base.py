"""Adapter interface + generic raw-payload adapter.

Future real providers (e.g. Razorpay webhooks) implement `EventAdapter` and
translate their raw payload into a `CanonicalEvent`; nothing else in the
pipeline needs to change.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from app.ingestion.models import CanonicalEvent


def parse_timestamp(raw: Any) -> Optional[datetime]:
    """Parse a timestamp from common string forms (ISO-8601 preferred).

    Returns None when the value cannot be parsed — the validator then
    rejects the event structurally (never silently discarded).
    """
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_uuid(raw: Any) -> Optional[uuid.UUID]:
    if isinstance(raw, uuid.UUID):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return uuid.UUID(raw.strip())
        except ValueError:
            return None
    return None


class EventAdapter(ABC):
    """Interface every source adapter implements.

    The adapter is responsible for extracting the canonical fields from a
    raw representation. Normalization (event type/source mapping) is done
    later by the pipeline, never by the adapter.
    """

    @abstractmethod
    def to_canonical(self, raw: Any) -> CanonicalEvent:
        """Translate a raw source representation into a CanonicalEvent."""

    def to_canonical_events(self, raw: Any) -> list[CanonicalEvent]:
        """Translate one raw source representation into canonical event(s).

        Most adapters produce exactly one event; the default delegates to
        `to_canonical`. Multi-event adapters (e.g. a webhook delivery that
        implies both a payment-state change and a WEBHOOK_RECEIVED record)
        override this so the pipeline stays uniform.
        """
        return [self.to_canonical(raw)]


class RawEventAdapter(EventAdapter):
    """Adapter for generic dict payloads (future webhook/provider bodies).

    Accepted field names (all optional except type + timestamp + identity):

        event_id | id                 -> event id
        event_type | type             -> raw event type
        source                        -> raw source
        timestamp | created_at | occurred_at
        order_id | payment_id | correlation_id
        idempotency_key
        payload                       -> original payload, preserved as-is
    """

    def to_canonical(self, raw: Any) -> CanonicalEvent:
        if not isinstance(raw, dict):
            raise ValueError(
                "RawEventAdapter expects a dict payload, got "
                f"{type(raw).__name__}"
            )
        timestamp = parse_timestamp(
            raw.get("timestamp")
            or raw.get("created_at")
            or raw.get("occurred_at")
            or raw.get("time")
        )
        return CanonicalEvent(
            event_id=str(
                raw.get("event_id") or raw.get("id") or uuid.uuid4()
            ),
            event_type=raw.get("event_type") or raw.get("type") or "",
            source=raw.get("source") or "",
            timestamp=timestamp,  # type: ignore[arg-type]
            order_id=_parse_uuid(raw.get("order_id")),
            payment_id=_parse_uuid(raw.get("payment_id")),
            correlation_id=_parse_uuid(raw.get("correlation_id")),
            idempotency_key=raw.get("idempotency_key"),
            # Original payload preserved untouched.
            payload=dict(raw.get("payload") or {}),
            original_event_reference={
                "kind": "raw_payload",
                "raw_keys": sorted(raw.keys()),
            },
        )