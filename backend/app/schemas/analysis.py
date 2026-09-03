"""Read API contract for the combined analysis package (Parts 4 + 5 + 6).

GET /api/v1/analysis/{transaction_id} returns the deterministic analysis
package: reconstructed journey + evidence report + consistency report +
business-outcome classification + compound-failure analysis + consequence /
impact analysis.

It is ONLY a deterministic analysis package — it is never called "AI
analysis". Every layer is computed by deterministic rules over the raw
records; no LLM, no simulation, no recommendation.
"""

from pydantic import BaseModel

from app.schemas.consistency import ConsistencyResult
from app.schemas.evidence import EvidenceReport
from app.schemas.failures import CompoundFailureResponse
from app.schemas.impact import ImpactResponse
from app.schemas.journeys import JourneyResponse
from app.schemas.outcome import OutcomeResponse


class AnalysisResponse(BaseModel):
    """Journey + evidence + consistency + outcome + failure + impact."""

    transaction_id: str
    journey: JourneyResponse
    evidence: EvidenceReport
    consistency: ConsistencyResult
    outcome: OutcomeResponse
    compound_failure: CompoundFailureResponse
    impact: ImpactResponse
