"""Read-only combined analysis endpoint (Part 4).

GET /api/v1/analysis/{transaction_id} — the deterministic analysis package
for one transaction: reconstructed journey + evidence report + consistency
report, computed in a single pipeline. Unknown or invalid transaction ids
return 404.

The output is ONLY a deterministic analysis package. It is not AI analysis
and it does not classify the business outcome.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analysis import AnalysisResponse
from app.services import analysis_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/{transaction_id}", response_model=AnalysisResponse)
def get_analysis(transaction_id: str, db: Session = Depends(get_db)):
    """The combined deterministic analysis package for one transaction."""
    try:
        response = analysis_service.get_analysis(db, transaction_id)
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