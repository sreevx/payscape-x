"""Read-only Outcome Engine endpoint (Part 5).

GET /api/v1/outcome/{transaction_id} — deterministic business-outcome
classification (FULFILLED / AT_RISK / FAILED / UNVERIFIABLE) for one
transaction. Unknown or invalid transaction ids return 404.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.outcome import OutcomeResponse
from app.services import outcome_service

router = APIRouter(prefix="/outcome", tags=["outcome"])


@router.get("/{transaction_id}", response_model=OutcomeResponse)
def get_outcome(transaction_id: str, db: Session = Depends(get_db)):
    """The deterministic business outcome for one transaction."""
    try:
        response = outcome_service.get_outcome(db, transaction_id)
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