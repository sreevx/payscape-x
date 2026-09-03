"""Razorpay TEST-MODE webhook adapter (Part 9).

Translates a Razorpay webhook event (raw provider payload) into the same
canonical events the synthetic dataset produces, so the existing Part 3
pipeline handles real Razorpay TEST-MODE deliveries with zero pipeline
changes:

    payment.captured  -> PAYMENT_CAPTURED (PAYMENT_PROVIDER)
                         + WEBHOOK_RECEIVED (WEBHOOK)
    payment.failed    -> PAYMENT_FAILED + WEBHOOK_RECEIVED
    payment.authorized-> PAYMENT_AUTHORIZED + WEBHOOK_RECEIVED
    payment.created   -> PAYMENT_CREATED + WEBHOOK_RECEIVED
    refund.created    -> REFUND_INITIATED + WEBHOOK_RECEIVED
    refund.processed  -> REFUND_COMPLETED + WEBHOOK_RECEIVED
    refund.failed     -> REFUND_FAILED + WEBHOOK_RECEIVED
    anything else     -> one UNKNOWN-marked event (preserved, never dropped)

Event-type spelling is kept RAW — normalization is the pipeline's job, never
the adapter's. Idempotency keys are derived deterministically so a
redelivered event cannot create duplicate canonical events.
"""

from typing import Any

from app.ingestion.adapters.base import EventAdapter
from app.ingestion.models import CanonicalEvent
from app.ingestion.razorpay import (
    SUPPORTED_WEBHOOK_EVENTS,
    extract_event_id,
    extract_event_timestamp,
    extract_event_type,
    extract_provider_payment_id,
)


class RazorpayWebhookAdapter(EventAdapter):
    """Adapter for Razorpay webhook event payloads (TEST MODE)."""

    def to_canonical(self, raw: Any) -> CanonicalEvent:
        """The primary (payment-state) canonical event of a webhook delivery."""
        return self.to_canonical_events(raw)[0]

    def to_canonical_events(self, raw: Any) -> list[CanonicalEvent]:
        if not isinstance(raw, dict):
            raise ValueError(
                "RazorpayWebhookAdapter expects a webhook event dict, got "
                f"{type(raw).__name__}"
            )
        event_type = extract_event_type(raw)
        timestamp = extract_event_timestamp(raw)
        provider_payment_id = extract_provider_payment_id(raw)
        provider_event_id = extract_event_id(raw)

        payload = {
            "provider": "razorpay",
            "provider_event_id": provider_event_id,
            "event": event_type,
        }
        if provider_payment_id:
            payload["provider_payment_id"] = provider_payment_id
        # The original provider payload is preserved untouched, keyed by
        # `raw` — nothing is ever disconnected from its origin.
        payload["raw"] = dict(raw)

        events: list[CanonicalEvent] = []
        if event_type in SUPPORTED_WEBHOOK_EVENTS:
            # The payment-state event mirrors the synthetic PAYMENT_CAPTURED
            # / PAYMENT_FAILED / ... rows from source PAYMENT_PROVIDER.
            events.append(
                CanonicalEvent(
                    event_id=f"razorpay:{provider_event_id}",
                    event_type=event_type,
                    source="razorpay",  # normalized -> PAYMENT_PROVIDER
                    timestamp=timestamp,  # type: ignore[arg-type]
                    idempotency_key=f"razorpay:{event_type}:{provider_event_id}",
                    payload=dict(payload),
                    original_event_reference={
                        "kind": "razorpay_webhook",
                        "event_id": provider_event_id,
                        "event": event_type,
                    },
                )
            )
        else:
            # Unknown provider event — preserved as-is, marked UNKNOWN by the
            # normalizer. Never guessed, never dropped.
            events.append(
                CanonicalEvent(
                    event_id=f"razorpay:{provider_event_id}",
                    event_type=event_type or "unknown_event",
                    source="razorpay",
                    timestamp=timestamp,  # type: ignore[arg-type]
                    idempotency_key=f"razorpay:{event_type}:{provider_event_id}",
                    payload=dict(payload),
                    original_event_reference={
                        "kind": "razorpay_webhook_unknown",
                        "event_id": provider_event_id,
                        "event": event_type,
                    },
                )
            )

        # The webhook delivery record itself (mirrors WEBHOOK_RECEIVED).
        events.append(
            CanonicalEvent(
                event_id=f"razorpay_webhook:{provider_event_id}",
                event_type="webhook.received",
                source="webhook",  # normalized -> WEBHOOK
                timestamp=timestamp,  # type: ignore[arg-type]
                idempotency_key=f"razorpay_webhook:{provider_event_id}",
                payload=dict(payload),
                original_event_reference={
                    "kind": "razorpay_webhook_delivery",
                    "event_id": provider_event_id,
                },
            )
        )
        return events