"""API contract for Razorpay TEST-MODE webhook ingestion (Part 9).

POST /api/v1/webhooks/razorpay accepts one Razorpay webhook event, verifies
its signature (when a secret is configured), records the raw delivery and
passes the event through the existing Part 3 ingestion pipeline
(adapter -> validate -> normalize -> correlate -> persist).

Every response item is labelled so DEMO / SYNTHETIC data is never confused
with a verified Razorpay TEST-MODE delivery:

- mode "razorpay_test_mode"     — signature verified against the configured
                                  webhook secret
- mode "demo"                   — explicit demo-mode delivery accepted only
                                  when DEMO_MODE=true and no secret is
                                  configured; signature_verified=false
- signature_verified            — false never implies a verified delivery

Nothing here executes a refund, payment or any financial action.
"""

from pydantic import BaseModel, ConfigDict


class WebhookIngestionItem(BaseModel):
    """The result of one canonical event through the Part 3 pipeline."""

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    source: str
    status: str          # PERSISTED | DUPLICATE | ORPHAN | UNKNOWN | REJECTED
    message: str
    persisted_event_id: str | None = None
    duplicate_of_event_id: str | None = None
    correlation_id: str | None = None


class RazorpayWebhookResponse(BaseModel):
    """Result of ingesting one Razorpay webhook delivery."""

    model_config = ConfigDict(from_attributes=True)

    mode: str                          # razorpay_test_mode | demo
    signature_verified: bool
    event: str                         # raw provider event type
    event_id: str                      # deterministic provider event identity
    provider_payment_id: str | None = None
    correlation_id: str | None = None
    webhook_row_id: str | None = None
    webhook_processing_status: str | None = None
    ingestion: list[WebhookIngestionItem] = []
    message: str