"""Read-only scenario endpoints (Part 2)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.scenarios import ScenarioDetailResponse, ScenarioSummary
from app.services import scenarios_service

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioSummary])
def list_scenarios(db: Session = Depends(get_db)):
    """Every synthetic scenario type with generated transaction counts."""
    try:
        return scenarios_service.list_scenarios(db)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="The data layer is unavailable. Run migrations and seed first.",
        ) from exc


@router.get("/{scenario_id}", response_model=ScenarioDetailResponse)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    """Scenario definition + its transactions, event count and timeline."""
    try:
        detail = scenarios_service.get_scenario(db, scenario_id)
    except sqlalchemy_exc.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="The data layer is unavailable. Run migrations and seed first.",
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return detail