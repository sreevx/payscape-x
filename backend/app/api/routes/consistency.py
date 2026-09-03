"""Read-only Consistency Engine endpoint (Part 4).

GET /api/v1/consistency/{transaction_id} — deterministic rule evaluation
for one transaction: PASS / VIOLATION / INSUFFICIENT_EVIDENCE /
NOT_APPLICABLE per rule plus overall_integrity (record agreement only,
never a business outcome). Unknown or invalid transaction ids return 404.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.consistency import ConsistencyResult
from app.services import consistency_service

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get("/{transaction_id}", response_model=ConsistencyResult)
def get_consistency(transaction_id: str, db: Session = Depends(get_db)):
    """The deterministic consistency report for one transaction."""
    try:
        response = consistency_service.get_consistency(db, transaction_id)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response