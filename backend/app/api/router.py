"""Aggregated API router.

Part 2 added read-only resources for transactions, the unified event stream
and synthetic scenarios. Part 3 adds journey reconstruction endpoints.
Part 4 adds evidence, consistency and the combined analysis package.
Part 5 adds the business-outcome classification. Part 6 adds compound
failure + consequence/impact analysis. Part 7 adds the read-only
Simulation Lab (baseline + intervention comparison). Part 8 adds the AI
Decision Agent with human approval — all under /api/v1.
"""

from fastapi import APIRouter

from app.api.routes.analysis import router as analysis_router
from app.api.routes.consistency import router as consistency_router
from app.api.routes.decisions import router as decisions_router
from app.api.routes.events import router as events_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.failures import router as failures_router
from app.api.routes.health import router as health_router
from app.api.routes.impact import router as impact_router
from app.api.routes.journeys import router as journeys_router
from app.api.routes.outcome import router as outcome_router
from app.api.routes.scenarios import router as scenarios_router
from app.api.routes.simulations import router as simulations_router
from app.api.routes.transactions import router as transactions_router
from app.api.routes.webhooks import router as webhooks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(transactions_router)
api_router.include_router(events_router)
api_router.include_router(scenarios_router)
api_router.include_router(journeys_router)
api_router.include_router(evidence_router)
api_router.include_router(consistency_router)
api_router.include_router(analysis_router)
api_router.include_router(outcome_router)
api_router.include_router(failures_router)
api_router.include_router(impact_router)
api_router.include_router(simulations_router)
api_router.include_router(decisions_router)
api_router.include_router(webhooks_router)