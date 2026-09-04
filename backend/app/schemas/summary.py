"""Response contract for GET /api/v1/summary (read-only dashboard aggregates).

Counts are computed by the existing deterministic Part 5 outcome engine
over every seeded journey — never a second outcome calculation — and the
payment metrics come straight from the `payments` table. Rates are
rounded to one decimal place over `total_transactions`.
"""

from datetime import datetime

from pydantic import BaseModel


class OutcomeCounts(BaseModel):
    """Deterministic business-outcome buckets across all journeys."""

    fulfilled: int
    at_risk: int
    failed: int
    unverifiable: int


class SummaryResponse(BaseModel):
    """Real dashboard aggregates for the seeded dataset."""

    total_transactions: int
    # Payment lifecycle (from the payments table): a successful payment is
    # any terminal capture (CAPTURED / REFUNDED / PARTIALLY_REFUNDED).
    payment_success_count: int
    payment_failed_count: int
    payment_pending_count: int
    payment_success_rate: float
    payment_failed_rate: float
    # Deterministic Part 5 outcome buckets + rates.
    outcomes: OutcomeCounts
    fulfilled_rate: float
    at_risk_rate: float
    failed_rate: float
    unverifiable_rate: float
    source: str
    computed_at: datetime
