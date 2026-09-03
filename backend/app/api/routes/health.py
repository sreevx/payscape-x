"""Health endpoint.

Served at `/health` (root, via main.py) and at `/api/v1/health`
(via the versioned api router).
"""

from fastapi import APIRouter

from app.core import database
from app.schemas.health import HealthResponse
from app.services.health_service import build_health_response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return build_health_response(database.get_engine())