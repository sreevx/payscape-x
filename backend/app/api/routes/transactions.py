"""Read-only transaction endpoints (Part 2).

A "transaction" is a payment-level journey: payment + order + customer +
correlation-id-correlated scenario + chronological events.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.transactions import (
    TransactionDetailResponse,
    TransactionListItem,
    TransactionListResponse,
)
from app.services import transactions_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _run(fn, *args):
    try:
        return fn(*args)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scenario: Optional[str] = Query(None, description="Scenario slug or type"),
    payment_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    """Paginated transactions with optional scenario / status filters."""
    items, total = _run(
        transactions_service.list_transactions,
        db,
        limit,
        offset,
        scenario,
        payment_status,
    )
    return TransactionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Full journey view: order, payment, customer, scenario, events."""
    detail = _run(transactions_service.get_transaction, db, transaction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return detail