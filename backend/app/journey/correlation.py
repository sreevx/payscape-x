"""Deterministic correlation resolution (Part 3).

When an event reaches the pipeline without an explicit correlation id, the
correlation is resolved with this documented priority order — never with
fuzzy semantic matching:

    1. explicit `correlation_id` on the event
    2. `order_id`    -> correlation of the order's existing journey events
    3. `payment_id`  -> correlation of the payment's existing journey events
    4. provider identifiers in the payload (`provider_payment_id`)
       -> payment -> that payment's journey correlation
    5. other explicit foreign keys / domain relationships
       (future providers add adapters here; same pattern as 4)

If no identity resolves, the event is preserved as an ORPHAN. Never guess.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import CanonicalEvent
from app.models import Payment, TransactionEvent


def _correlation_for(session: Session, **criteria) -> Optional[uuid.UUID]:
    """Most recent journey correlation matching the given criteria."""
    statement = (
        select(TransactionEvent.correlation_id)
        .where(
            *[
                getattr(TransactionEvent, column) == value
                for column, value in criteria.items()
            ]
        )
        .order_by(
            TransactionEvent.timestamp.desc(),
            TransactionEvent.id.desc(),
        )
        .limit(1)
    )
    return session.scalar(statement)


def resolve_correlation(
    session: Session, event: CanonicalEvent
) -> tuple[Optional[uuid.UUID], Optional[str]]:
    """Resolve a canonical event's journey correlation.

    Returns (correlation_id, reason). reason is None when unresolved — the
    caller preserves the event as an orphan.
    """
    # 1. Explicit correlation id wins.
    if event.correlation_id is not None:
        return event.correlation_id, "explicit_correlation_id"

    # 2. order_id -> correlation of the order's existing journey.
    if event.order_id is not None:
        correlation = _correlation_for(session, order_id=event.order_id)
        if correlation is not None:
            return correlation, "order_id"

    # 3. payment_id -> correlation of the payment's existing journey.
    if event.payment_id is not None:
        correlation = _correlation_for(session, payment_id=event.payment_id)
        if correlation is not None:
            return correlation, "payment_id"

    # 4. Provider identifiers inside the payload.
    provider_payment_id = (event.payload or {}).get("provider_payment_id")
    if provider_payment_id:
        payment = session.scalars(
            select(Payment).where(
                Payment.provider_payment_id == str(provider_payment_id)
            ).limit(1)
        ).first()
        if payment is not None:
            correlation = _correlation_for(session, payment_id=payment.id)
            if correlation is not None:
                return correlation, "provider_payment_id"

    # 5. No deterministic identity — orphan. Never guess.
    return None, None