"""Read-only Simulation Lab endpoints (Part 7).

GET  /api/v1/simulations/{transaction_id}         — baseline + every
                                                   intervention's simulated
                                                   result + ranked comparison
POST /api/v1/simulations/{transaction_id}/run     — run ONE intervention
GET  /api/v1/simulations/{transaction_id}/compare — ranked comparison table

The lab is deterministic and strictly read-only: nothing here modifies
payments, orders, inventory, refunds or webhooks. Unknown transaction ids
return 404; an unknown intervention type on /run returns 400.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.simulation import (
    RunSimulationRequest,
    SimulationReport,
    SimulationResultItem,
)
from app.services import simulation_service
from app.simulation.models import ALL_INTERVENTIONS

router = APIRouter(prefix="/simulations", tags=["simulations"])


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


@router.get("/{transaction_id}", response_model=SimulationReport)
def get_simulations(transaction_id: str, db: Session = Depends(get_db)):
    """Baseline + simulated results for every available intervention."""
    response = _run(simulation_service.get_simulations, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response


@router.post("/{transaction_id}/run", response_model=SimulationResultItem)
def run_simulation(
    transaction_id: str,
    request: RunSimulationRequest,
    db: Session = Depends(get_db),
):
    """Run ONE deterministic intervention for the transaction."""
    if request.intervention not in ALL_INTERVENTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown intervention '{request.intervention}'. Valid "
                f"interventions: {', '.join(ALL_INTERVENTIONS)}."
            ),
        )
    response = _run(
        simulation_service.get_single_result, db, transaction_id,
        request.intervention,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response


@router.get("/{transaction_id}/compare", response_model=SimulationReport)
def compare_simulations(transaction_id: str, db: Session = Depends(get_db)):
    """Ranked comparison of the applicable interventions."""
    response = _run(simulation_service.get_simulations, db, transaction_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response
