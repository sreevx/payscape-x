"""AI Decision Agent endpoints (Part 8).

GET  /api/v1/decisions/{transaction_id}           — generate (idempotently
                                                    persist) the auditable
                                                    decision
POST /api/v1/decisions/{decision_id}/approve      — PENDING -> APPROVED
POST /api/v1/decisions/{decision_id}/reject       — PENDING -> REJECTED
                                                    (optional reason)

Safety: approve/reject only record the merchant's decision on the
`decisions` row. Nothing here executes refunds, payments, messages or any
external action, and the recommendation is always validated against the
verified Parts 1-7 facts (invalid LLM output falls back deterministically).

Unknown transaction ids return 404; invalid approval transitions on a
final decision return 409; an unknown decision_id returns 404.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.decision import (
    ApproveDecisionRequest,
    DecisionResponse,
    RejectDecisionRequest,
)
from app.services import decision_service
from app.services.decision_service import DecisionStateError

router = APIRouter(prefix="/decisions", tags=["decisions"])


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


@router.get("/{transaction_id}", response_model=DecisionResponse)
def get_decision(transaction_id: str, db: Session = Depends(get_db)):
    """Generate (idempotently persist) the decision for one transaction."""
    response = _run(decision_service.get_decision, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response


@router.post("/{decision_id}/approve", response_model=DecisionResponse)
def approve_decision(
    decision_id: str,
    request: Optional[ApproveDecisionRequest] = None,
    db: Session = Depends(get_db),
):
    """Record merchant approval (PENDING -> APPROVED). Never executes."""
    note = request.note if request is not None else None
    try:
        response = _run(
            decision_service.approve_decision, db, decision_id, note
        )
    except DecisionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return response


@router.post("/{decision_id}/reject", response_model=DecisionResponse)
def reject_decision(
    decision_id: str,
    request: Optional[RejectDecisionRequest] = None,
    db: Session = Depends(get_db),
):
    """Record merchant rejection (PENDING -> REJECTED). Never executes."""
    reason = request.reason if request is not None else None
    try:
        response = _run(
            decision_service.reject_decision, db, decision_id, reason
        )
    except DecisionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return response