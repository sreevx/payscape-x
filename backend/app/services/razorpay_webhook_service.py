"""Razorpay TEST-MODE webhook service (Part 9).

Composition layer between the webhook route and the existing Part 3
pipeline. It:

1. verifies the delivery (HMAC signature when a secret is configured; an
   explicit demo-mode bypass when no secret is configured and DEMO_MODE is
   on — never pretending an unverified delivery was verified)
2. records the raw delivery as a `Webhook` row (audit trail) when the
   payment is deterministically linked
3. translates the provider payload with `RazorpayWebhookAdapter` and runs
   EVERY canonical event through the exact Part 3 ingestion pipeline
   (validate -> normalize -> correlate -> idempotency -> persist)

Safety contract:

- No financial action is ever performed — no refunds, no payments, no
  external calls. The system stops at recording the delivery + canonical
  events into the unified stream.
- A redelivered event (same provider event id) is idempotent: the second
  delivery records a DUPLICATE webhook row and persists zero new events.
- A webhook whose payment cannot be linked is preserved as an ORPHAN in
  the response and nothing is persisted — never guessed, never invented.
- Secrets never appear in logs, messages or the response.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import WebhookProcessingStatus
from app.ingestion.adapters.base import RawEventAdapter
from app.ingestion.adapters.razorpay import RazorpayWebhookAdapter
from app.ingestion.razorpay import (
    RazorpayWebhookError,
    extract_event_id,
    extract_event_type,
    extract_provider_payment_id,
    parse_event_body,
    verify_signature,
)
from app.ingestion.service import IngestionService
from app.models import Payment, Webhook
from app.schemas.webhook import RazorpayWebhookResponse, WebhookIngestionItem

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "x-razorpay-signature"
DEMO_HEADER = "x-payscape-demo"


def process_razorpay_webhook(
    session: Session,
    body: bytes,
    signature: Optional[str] = None,
    demo_header: Optional[str] = None,
    *,
    secret: Optional[str] = None,
    demo_mode: Optional[bool] = None,
) -> RazorpayWebhookResponse:
    """Verify + ingest one Razorpay webhook delivery. Deterministic."""
    settings = get_settings()
    configured_secret = (
        secret if secret is not None else settings.razorpay_webhook_secret
    )
    configured_demo = (
        demo_mode if demo_mode is not None else settings.demo_mode
    )

    # 1. Signature verification — strict when a secret is configured.
    mode: str
    signature_verified: bool
    if configured_secret:
        if not signature:
            raise RazorpayWebhookError(
                400, "Missing X-Razorpay-Signature header"
            )
        if not verify_signature(body, signature, configured_secret):
            raise RazorpayWebhookError(
                400, "Invalid X-Razorpay-Signature — delivery rejected"
            )
        mode = "razorpay_test_mode"
        signature_verified = True
    elif configured_demo and (demo_header or "").strip() == "1":
        # Explicit demo-mode delivery: no secret configured, so the
        # signature cannot be verified. Recorded as unverified — never
        # presented as a verified delivery.
        mode = "demo"
        signature_verified = False
    else:
        raise RazorpayWebhookError(
            400,
            "Razorpay webhook secret not configured; signature cannot be "
            "verified. Configure RAZORPAY_WEBHOOK_SECRET or, in demo mode "
            "only, send X-PAYSCAPE-DEMO: 1 for an explicitly unverified "
            "demo delivery.",
        )

    # 2. Parse + extract deterministic identities.
    event = parse_event_body(body)
    event_type = extract_event_type(event)
    event_id = extract_event_id(event)
    provider_payment_id = extract_provider_payment_id(event)

    adapter = RazorpayWebhookAdapter()
    canonical_events = adapter.to_canonical_events(event)

    # 3. Deterministic payment linking (explicit provider identifier only).
    payment = _find_payment(session, provider_payment_id)
    if payment is None:
        # No deterministic link — run the pipeline so the event is
        # preserved as an ORPHAN in the response; nothing is persisted.
        ingestion = [
            _ingest_item(session, event_id=canonical.event_id, canonical=canonical)
            for canonical in canonical_events
        ]
        return RazorpayWebhookResponse(
            mode=mode,
            signature_verified=signature_verified,
            event=event_type or "unknown_event",
            event_id=event_id,
            provider_payment_id=provider_payment_id,
            correlation_id=None,
            webhook_row_id=None,
            webhook_processing_status=None,
            ingestion=ingestion,
            message=(
                "No matching Razorpay payment found — the event is "
                "preserved as an ORPHAN and nothing was persisted."
            ),
        )

    # 4. Record the raw delivery (audit trail) — status finalized below.
    received_at = datetime.now(timezone.utc)
    webhook_row = Webhook(
        payment_id=payment.id,
        provider="razorpay",
        event_type=event_type or "unknown_event",
        provider_event_id=event_id,
        received_at=received_at,
        delivered_at=received_at,
        signature_verified=signature_verified,
        payload=event,
        processing_status=WebhookProcessingStatus.RECEIVED,
    )
    session.add(webhook_row)

    # 5. Pass every canonical event through the existing Part 3 pipeline.
    ingestion: list[WebhookIngestionItem] = []
    for canonical in canonical_events:
        ingestion.append(
            _ingest_item(session, event_id=canonical.event_id, canonical=canonical)
        )

    # 6. Finalize the delivery record's processing status.
    statuses = [item.status for item in ingestion]
    if "REJECTED" in statuses:
        webhook_row.processing_status = WebhookProcessingStatus.FAILED
    elif "DUPLICATE" in statuses:
        webhook_row.processing_status = WebhookProcessingStatus.DUPLICATE
    elif "UNKNOWN" in statuses:
        webhook_row.processing_status = WebhookProcessingStatus.FAILED
    else:
        webhook_row.processing_status = WebhookProcessingStatus.PROCESSED
    session.commit()
    session.refresh(webhook_row)

    # Correlation of the journey the events joined (read back, not guessed).
    correlation_id = _correlation_of(session, ingestion)

    return RazorpayWebhookResponse(
        mode=mode,
        signature_verified=signature_verified,
        event=event_type or "unknown_event",
        event_id=event_id,
        provider_payment_id=provider_payment_id,
        correlation_id=str(correlation_id) if correlation_id else None,
        webhook_row_id=str(webhook_row.id),
        webhook_processing_status=webhook_row.processing_status.value,
        ingestion=ingestion,
        message=(
            "Webhook delivery recorded and passed through the Part 3 "
            "ingestion pipeline (validate -> normalize -> correlate -> "
            "idempotency -> persist). No financial action was performed."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_payment(
    session: Session, provider_payment_id: Optional[str]
) -> Optional[Payment]:
    if not provider_payment_id:
        return None
    return session.scalars(
        select(Payment).where(
            Payment.provider == "razorpay",
            Payment.provider_payment_id == str(provider_payment_id),
        ).limit(1)
    ).first()


def _ingest_item(session: Session, event_id: str, canonical) -> WebhookIngestionItem:
    """Run one canonical event through the Part 3 ingestion pipeline."""
    # The adapter has already produced canonical events; feed them through
    # the pipeline via the raw-payload path without re-translating.
    service = IngestionService(adapter=_IdentityAdapter())
    result = service.ingest(session, canonical)
    return WebhookIngestionItem(
        event_id=result.event.event_id or event_id,
        event_type=result.event.event_type,
        source=result.event.source,
        status=result.status.value,
        message=result.message,
        persisted_event_id=result.persisted_event_id,
        duplicate_of_event_id=result.duplicate_of_event_id,
        correlation_id=(
            str(result.event.correlation_id)
            if result.event.correlation_id is not None
            else None
        ),
    )


class _IdentityAdapter(RawEventAdapter):
    """Adapter that returns the canonical event unchanged.

    `RazorpayWebhookAdapter` already produced canonical events; this shim
    feeds them into the identical validate -> normalize -> correlate ->
    persist pipeline without re-translating the raw provider payload.
    """

    def to_canonical(self, raw):
        return raw


def _correlation_of(
    session: Session, ingestion: list[WebhookIngestionItem]
) -> Optional[str]:
    """Read the journey correlation back from the persisted events."""
    import uuid

    from app.models import TransactionEvent

    for item in ingestion:
        if not item.persisted_event_id:
            continue
        try:
            row_id = uuid.UUID(item.persisted_event_id)
        except ValueError:
            continue
        row = session.get(TransactionEvent, row_id)
        if row is not None and row.correlation_id is not None:
            return str(row.correlation_id)
    return None