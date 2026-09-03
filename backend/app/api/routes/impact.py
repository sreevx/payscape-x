"""Read-only Consequence / Impact endpoint (Part 6).

GET /api/v1/impact/{transaction_id} — downstream consequences + impact
analysis for one transaction (observed / derived / potential, single vs
multi-transaction scope, transparent impact score). Unknown or invalid
transaction ids return 404.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.impact import ImpactResponse
from app.services import impact_service

router = APIRouter(prefix="/impact", tags=["impact"])


@router.get("/{transaction_id}", response_model=ImpactResponse)
def get_impact(transaction_id: str, db: Session = Depends(get_db)):
    """Consequence / impact analysis for one transaction."""
    try:
        response = impact_service.get_impact(db, transaction_id)
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
