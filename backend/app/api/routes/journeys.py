"""Read-only journey reconstruction endpoints (Part 3).

GET /api/v1/journeys/{transaction_id}          — events + graph + integrity
GET /api/v1/journeys/{transaction_id}/graph    — deterministic graph only
GET /api/v1/journeys/{transaction_id}/integrity — structural integrity only

All output is deterministic. Unknown or invalid transaction ids return 404.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.journeys import (
    JourneyGraphResponse,
    JourneyIntegrityResponse,
    JourneyResponse,
)
from app.services import journeys_service

router = APIRouter(prefix="/journeys", tags=["journeys"])


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


@router.get("/{transaction_id}", response_model=JourneyResponse)
def get_journey(transaction_id: str, db: Session = Depends(get_db)):
    """The full reconstructed journey for one transaction."""
    response = _run(journeys_service.get_journey, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response


@router.get("/{transaction_id}/graph", response_model=JourneyGraphResponse)
def get_journey_graph(transaction_id: str, db: Session = Depends(get_db)):
    """The deterministic journey graph for one transaction."""
    response = _run(journeys_service.get_journey_graph, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response


@router.get("/{transaction_id}/integrity", response_model=JourneyIntegrityResponse)
def get_journey_integrity(transaction_id: str, db: Session = Depends(get_db)):
    """The structural integrity report for one transaction."""
    response = _run(journeys_service.get_journey_integrity, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response