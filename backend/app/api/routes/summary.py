"""Read-only dashboard summary endpoint (Phase B).

GET /api/v1/summary — real dashboard aggregates computed from the seeded
dataset by the existing deterministic Part 5 outcome engine (never a
second outcome calculation). Read-only; no mutation of any record.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.summary import SummaryResponse
from app.services import summary_service

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("", response_model=SummaryResponse)
def get_summary(db: Session = Depends(get_db)):
    """Real dashboard aggregates over the seeded dataset (deterministic)."""
    try:
        return summary_service.get_summary(db)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc
