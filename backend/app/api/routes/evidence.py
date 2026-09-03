"""Read-only Evidence Engine endpoint (Part 4).

GET /api/v1/evidence/{transaction_id} — deterministic evidence report for
one transaction: structured claims, evidence gaps and preserved
contradictions. Unknown or invalid transaction ids return 404.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.evidence import EvidenceReport
from app.services import evidence_service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/{transaction_id}", response_model=EvidenceReport)
def get_evidence(transaction_id: str, db: Session = Depends(get_db)):
    """The deterministic evidence report for one transaction."""
    try:
        response = evidence_service.get_evidence(db, transaction_id)
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