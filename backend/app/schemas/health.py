"""Health check contract."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response for GET /health and GET /api/v1/health.

    `status` reflects the service liveness; `database` reports connectivity
    separately so the API stays honest when PostgreSQL is unreachable.
    """

    status: Literal["ok"] = "ok"
    service: str
    version: str
    database: Literal["ok", "unavailable"]