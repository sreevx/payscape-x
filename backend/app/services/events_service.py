"""Read queries for the unified event stream."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, TransactionEvent
from app.schemas.events import EventStreamItem


def list_events(
    session: Session,
    limit: int,
    offset: int,
    event_type: Optional[str] = None,
    source: Optional[str] = None,
    correlation_id: Optional[str] = None,
):
    """Paginated unified event stream with filters (chronological order)."""
    correlation_uuid: Optional[uuid.UUID] = None
    if correlation_id:
        try:
            correlation_uuid = uuid.UUID(correlation_id)
        except (ValueError, AttributeError):
            return [], 0

    base = select(TransactionEvent.id)
    if event_type:
        base = base.where(TransactionEvent.event_type == event_type)
    if source:
        base = base.where(TransactionEvent.source == source)
    if correlation_uuid is not None:
        base = base.where(TransactionEvent.correlation_id == correlation_uuid)

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = session.execute(
        select(TransactionEvent, Order.external_order_id)
        .join(Order, TransactionEvent.order_id == Order.id)
        .where(TransactionEvent.id.in_(base))
        .order_by(TransactionEvent.timestamp.asc(), TransactionEvent.id)
        .offset(offset)
        .limit(limit)
    ).all()

    items = [
        EventStreamItem(
            id=str(event.id),
            order_id=str(event.order_id),
            external_order_id=external_order_id,
            payment_id=str(event.payment_id) if event.payment_id else None,
            event_type=event.event_type.value,
            source=event.source.value,
            timestamp=event.timestamp,
            correlation_id=str(event.correlation_id),
            idempotency_key=event.idempotency_key,
            payload=event.payload,
        )
        for event, external_order_id in rows
    ]
    return items, total