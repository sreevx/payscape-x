"""Read-only Compound Failure endpoints (Part 6).

GET /api/v1/failures/{transaction_id} — compound failure analysis for one
transaction.
GET /api/v1/failures — paginated dataset of detected compound failures
with optional severity / failure type / outcome / scope filters.

Responses are deterministic. Unknown or invalid transaction ids return 404.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.failures import (
    CompoundFailureResponse,
    FailureListResponse,
)
from app.services import failures_service

router = APIRouter(prefix="/failures", tags=["failures"])


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc


@router.get("", response_model=FailureListResponse)
def list_failures(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None, description="LOW | MEDIUM | HIGH | CRITICAL"),
    failure_type: Optional[str] = Query(
        None, description="Primary failure kind, e.g. INVENTORY_ALLOCATION_FAILED"
    ),
    outcome: Optional[str] = Query(None, description="FULFILLED | AT_RISK | FAILED | UNVERIFIABLE"),
    scope: Optional[str] = Query(
        None, description="SINGLE_TRANSACTION | MULTI_TRANSACTION"
    ),
    db: Session = Depends(get_db),
) -> FailureListResponse:
    """Detected compound failures across the seeded dataset."""
    items, total = _run(
        failures_service.list_failures,
        db,
        limit,
        offset,
        severity,
        failure_type,
        outcome,
        scope,
    )
    return FailureListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{transaction_id}", response_model=CompoundFailureResponse)
def get_failure(transaction_id: str, db: Session = Depends(get_db)):
    """Compound failure analysis for one transaction."""
    response = _run(failures_service.get_failure, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response
