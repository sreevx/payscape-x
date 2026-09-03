"""Razorpay TEST-MODE webhook support (Part 9).

Signature verification and payload parsing for Razorpay webhook deliveries.
This module contains ONLY provider-specific plumbing:

- `verify_signature` — HMAC-SHA256 over the RAW request body, compared in
  constant time against the `X-Razorpay-Signature` header (Razorpay's
  documented scheme). Never logs the secret; never accepts a missing or
  malformed signature when a secret is configured.
- `parse_event_body` — strict JSON parsing with a deterministic error.
- `extract_*` helpers — pull the deterministic identity fields out of a
  Razorpay event payload (payment id, entity id, event id, timestamp).

The endpoint that uses these helpers then hands the parsed event to the
Part 3 `RazorpayWebhookAdapter`, so every delivery flows through the exact
same pipeline as the synthetic dataset: adapter -> validate -> normalize ->
correlate -> persist. Nothing here performs financial actions; this is
TEST-MODE ingestion only.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional


class RazorpayWebhookError(Exception):
    """Structured rejection with an HTTP status and safe detail message."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def verify_signature(payload: bytes, signature: Optional[str], secret: str) -> bool:
    """Return True only when `signature` is a valid HMAC-SHA256 of payload.

    The comparison is constant-time (hmac.compare_digest) and the secret is
    never included in any message, log line or exception.
    """
    if not secret:
        return False
    if not signature:
        return False
    try:
        expected = base64.b64encode(
            hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        ).decode("ascii")
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, signature)


def parse_event_body(body: bytes) -> dict[str, Any]:
    """Parse a Razorpay webhook JSON body. Raises RazorpayWebhookError(400)."""
    if not body or not body.strip():
        raise RazorpayWebhookError(400, "Empty webhook body")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RazorpayWebhookError(
            400, "Malformed webhook body: expected a JSON object"
        ) from exc
    if not isinstance(parsed, dict):
        raise RazorpayWebhookError(
            400, "Malformed webhook body: expected a JSON object"
        )
    return parsed


# ---------------------------------------------------------------------------
# Deterministic identity extraction
# ---------------------------------------------------------------------------

# Razorpay event -> (entity key inside payload, canonical registry mapping is
# done later by the normalizer, never here).
_PAYMENT_ENTITY_EVENTS = frozenset(
    {
        "payment.created",
        "payment.authorized",
        "payment.captured",
        "payment.failed",
    }
)
_REFUND_ENTITY_EVENTS = frozenset(
    {
        "refund.created",
        "refund.processed",
        "refund.failed",
    }
)

# Supported webhook event types. Anything else is preserved and marked
# UNKNOWN by the pipeline — never deleted, never guessed at.
SUPPORTED_WEBHOOK_EVENTS: frozenset[str] = (
    _PAYMENT_ENTITY_EVENTS | _REFUND_ENTITY_EVENTS
)


def extract_provider_payment_id(event: dict[str, Any]) -> Optional[str]:
    """The Razorpay payment id an event concerns (pay_... / from refunds)."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    entity = payload.get("payment")
    if isinstance(entity, dict):
        inner = entity.get("entity")
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            return inner["id"]
    refund = payload.get("refund")
    if isinstance(refund, dict):
        inner = refund.get("entity")
        if isinstance(inner, dict) and isinstance(inner.get("payment_id"), str):
            return inner["payment_id"]
    return None


def extract_entity_id(event: dict[str, Any]) -> Optional[str]:
    """The entity id (pay_... / rfd_...) an event carries, if any."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    for key in ("payment", "refund"):
        entity = payload.get(key)
        if not isinstance(entity, dict):
            continue
        inner = entity.get("entity")
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            return inner["id"]
    return None


def extract_event_id(event: dict[str, Any]) -> str:
    """Deterministic webhook identity: top-level id, else the entity id.

    Razorpay redeliveries of the same event carry the same identity, which
    is what the Part 3 idempotency mechanism keys on.
    """
    top_level = event.get("id")
    if isinstance(top_level, str) and top_level.strip():
        return top_level
    entity_id = extract_entity_id(event)
    if entity_id:
        return entity_id
    return "unknown"


def extract_event_type(event: dict[str, Any]) -> str:
    raw = event.get("event")
    return raw if isinstance(raw, str) and raw.strip() else ""


def extract_event_timestamp(event: dict[str, Any]) -> Optional[datetime]:
    """Razorpay `created_at` (epoch seconds) -> timezone-aware datetime."""
    raw = event.get("created_at")
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc)