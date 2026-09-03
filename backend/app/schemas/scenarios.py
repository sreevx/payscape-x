"""Read API contract for synthetic scenarios."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ScenarioSummary(BaseModel):
    """One synthetic scenario type with its generated transaction count."""

    model_config = ConfigDict(from_attributes=True)

    scenario_id: str  # slug, e.g. "normal_success"
    scenario_type: str  # enum value, e.g. "NORMAL_SUCCESS"
    name: str
    description: str
    transaction_count: int = 0
    event_count: int = 0


class ScenarioTransactionItem(BaseModel):
    """A transaction belonging to a scenario."""

    id: str
    order_id: str
    external_order_id: str
    customer_name: str
    amount: Decimal
    currency: str
    payment_status: str
    created_at: datetime


class TimelineEventItem(BaseModel):
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: str


class ScenarioDetailResponse(BaseModel):
    scenario_id: str
    scenario_type: str
    name: str
    description: str
    correlation_count: int
    event_count: int
    transactions: list[ScenarioTransactionItem]
    timeline: list[TimelineEventItem]