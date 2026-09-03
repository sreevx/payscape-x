"""Read API contracts for transactions (payment-level journeys)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class TransactionListItem(BaseModel):
    """One payment-level transaction in list views.

    model_config: SQLAlchemy ORM objects may be passed in directly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    external_order_id: str
    customer_name: str
    customer_email: str
    amount: Decimal
    currency: str
    payment_status: str
    provider: str
    method: Optional[str] = None
    scenario_type: Optional[str] = None
    scenario_slug: Optional[str] = None
    event_count: int = 0
    created_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionListItem]
    total: int
    limit: int
    offset: int


class EventItem(BaseModel):
    """One unified TransactionEvent as exposed by the read API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    payment_id: Optional[str] = None
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str
    idempotency_key: Optional[str] = None
    payload: dict
    created_at: datetime


class TransactionDetailResponse(BaseModel):
    """Full transaction view: order, payment, customer, events, scenario."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    external_order_id: str
    customer_id: str
    customer_name: str
    customer_email: str
    merchant_name: str
    amount: Decimal
    currency: str
    order_status: str
    payment_status: str
    provider: str
    provider_payment_id: str
    method: Optional[str] = None
    captured_at: Optional[datetime] = None
    created_at: datetime
    scenario_type: Optional[str] = None
    scenario_slug: Optional[str] = None
    scenario_description: Optional[str] = None
    events: list[EventItem]


# Acceptable filter values (read-only endpoints).
TransactionStatusFilter = Literal[
    "CREATED", "AUTHORIZED", "CAPTURED", "FAILED", "REFUNDED",
    "PARTIALLY_REFUNDED",
]