"""Read API contract for the unified event stream."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EventStreamItem(BaseModel):
    """One unified event enriched with order context for the explorer."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    external_order_id: str
    payment_id: Optional[str] = None
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str
    idempotency_key: Optional[str] = None
    payload: dict


class EventStreamResponse(BaseModel):
    items: list[EventStreamItem]
    total: int
    limit: int
    offset: int