"""Analysis package service (Parts 4 + 5 + 6).

Composes the deterministic pipeline for one transaction:

    journey = reconstruct(transaction)
    evidence = collect(journey)
    consistency = evaluate(journey, evidence)
    outcome = decide(journey, integrity, evidence, consistency)
    failure = analyze_failure(journey, integrity, evidence, consistency, outcome)
    impact = analyze_impact(journey, integrity, evidence, consistency, outcome,
                            failure, cross)

The journey is reconstructed exactly once and shared by all six outputs.
Same input always produces byte-equivalent JSON (after normalization) — no
LLM, no external APIs, no randomness.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.analysis import AnalysisResponse
from app.services import journeys_service
from app.services.consistency_service import build_consistency, _result_schema
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence, _report_schema
from app.services.failures_service import build_failure, _failure_schema
from app.services.impact_service import (
    _impact_schema,
    build_impact,
    load_cross_transaction,
)
from app.services.outcome_service import build_outcome, _outcome_schema


def get_analysis(
    session: Session, transaction_id: str
) -> Optional[AnalysisResponse]:
    """Build the full deterministic analysis package. None when unknown."""
    payment_uuid = _resolve_transaction_id(transaction_id)
    if payment_uuid is None:
        return None
    result = journeys_service._reconstruct_all(session, transaction_id)
    if result is None:
        return None
    journey, integrity, graph = result

    context = load_domain_context(session, payment_uuid)
    if context is None:
        return None

    evidence = build_evidence(journey, integrity, context)
    consistency = build_consistency(journey, context)
    outcome = build_outcome(journey, integrity, evidence, consistency)
    failure = build_failure(journey, integrity, evidence, consistency, outcome)
    cross = load_cross_transaction(session, payment_uuid)
    impact = build_impact(
        journey, integrity, evidence, consistency, outcome, failure, cross
    )

    return AnalysisResponse(
        transaction_id=journey.transaction_id,
        journey=journeys_service._map_journey(journey, integrity, graph),
        evidence=_report_schema(evidence),
        consistency=_result_schema(consistency),
        outcome=_outcome_schema(outcome),
        compound_failure=_failure_schema(failure),
        impact=_impact_schema(impact),
    )


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None
