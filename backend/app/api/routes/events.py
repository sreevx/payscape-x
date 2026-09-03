"""Read-only unified event stream endpoints (Part 2)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.events import EventStreamResponse
from app.services import events_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventStreamResponse)
def list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> EventStreamResponse:
    """Chronological unified event stream with filters + pagination."""
    try:
        items, total = events_service.list_events(
            db, limit, offset, event_type, source, correlation_id
        )
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The data layer is unavailable. Run `alembic upgrade head` "
                "and `python -m app.seed` first."
            ),
        ) from exc
    return EventStreamResponse(items=items, total=total, limit=limit, offset=offset)