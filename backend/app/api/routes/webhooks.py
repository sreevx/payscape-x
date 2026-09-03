"""Razorpay TEST-MODE webhook endpoint (Part 9).

POST /api/v1/webhooks/razorpay

Accepts ONE Razorpay webhook event and runs it through the existing Part 3
ingestion pipeline (adapter -> validate -> normalize -> correlate ->
idempotency -> persist). Behavior:

- `RAZORPAY_WEBHOOK_SECRET` configured: the raw body's HMAC-SHA256
  signature is verified against `X-Razorpay-Signature`. Valid signatures
  are accepted; invalid or missing signatures are rejected with 400.
- No secret + DEMO_MODE: only explicit demo-mode deliveries
  (`X-PAYSCAPE-DEMO: 1`) are accepted, recorded as signature_verified=false.
- Without either, the request is rejected with 400.

The endpoint NEVER performs a financial action: it records the delivery and
canonical events only. Redeliveries are idempotent (no duplicate canonical
events); webhooks for unknown payments are preserved as ORPHAN in the
response and nothing is persisted.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ingestion.razorpay import RazorpayWebhookError
from app.schemas.webhook import RazorpayWebhookResponse
from app.services import razorpay_webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay", response_model=RazorpayWebhookResponse)
async def receive_razorpay_webhook(
    request: Request, db: Session = Depends(get_db)
):
    """Verify + ingest one Razorpay TEST-MODE webhook delivery."""
    body = await request.body()
    signature = request.headers.get(razorpay_webhook_service.SIGNATURE_HEADER)
    demo_header = request.headers.get(razorpay_webhook_service.DEMO_HEADER)
    try:
        return razorpay_webhook_service.process_razorpay_webhook(
            db, body, signature=signature, demo_header=demo_header
        )
    except RazorpayWebhookError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc