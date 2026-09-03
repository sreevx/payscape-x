"""Structural event validation (Part 3).

Checks that a canonical event is well-formed enough to enter the pipeline:

- has an event type and a parseable timestamp
- has at least one correlatable identity (order, payment or correlation)
- carries well-formed UUIDs and a dict payload

These are STRUCTURAL rules only. No business-state rules live here: a
capture followed by a failure is valid input to the pipeline (it will be
preserved and later surfaced as a contradiction by journey integrity, never
rejected at the door).
"""

import uuid
from typing import Optional

from app.ingestion.models import CanonicalEvent

MAX_IDEMPOTENCY_KEY_LENGTH = 128


def _valid_uuid(value: Optional[uuid.UUID]) -> bool:
    return isinstance(value, uuid.UUID)


def validate_event(event: CanonicalEvent) -> list[str]:
    """Return a list of structural problems (empty = valid)."""
    errors: list[str] = []

    if not isinstance(event.event_type, str) or not event.event_type.strip():
        errors.append("missing or empty event_type")

    if event.timestamp is None:
        errors.append("missing timestamp")
    elif not isinstance(event.timestamp, uuid.UUID) and not hasattr(
        event.timestamp, "tzinfo"
    ):
        errors.append("timestamp is not a datetime")

    # A provider identifier inside the payload is also a legitimate identity
    # (resolved later by correlation priority 4). Everything else is rejected
    # as structurally unlinkable — never guessed, never silently dropped.
    has_provider_identity = isinstance(event.payload, dict) and bool(
        event.payload.get("provider_payment_id")
    )
    if (
        event.order_id is None
        and event.payment_id is None
        and event.correlation_id is None
        and not has_provider_identity
    ):
        errors.append(
            "no correlatable identity: at least one of order_id, payment_id, "
            "correlation_id or payload.provider_payment_id is required"
        )
    if event.order_id is not None and not _valid_uuid(event.order_id):
        errors.append("order_id is not a valid UUID")
    if event.payment_id is not None and not _valid_uuid(event.payment_id):
        errors.append("payment_id is not a valid UUID")
    if event.correlation_id is not None and not _valid_uuid(event.correlation_id):
        errors.append("correlation_id is not a valid UUID")

    if event.idempotency_key is not None:
        if not isinstance(event.idempotency_key, str) or not event.idempotency_key:
            errors.append("idempotency_key must be a non-empty string")
        elif len(event.idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            errors.append(
                f"idempotency_key exceeds {MAX_IDEMPOTENCY_KEY_LENGTH} characters"
            )

    if not isinstance(event.payload, dict):
        errors.append("payload must be an object (dict)")

    return errors