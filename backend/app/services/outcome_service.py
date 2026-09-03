"""Outcome Engine service (Part 5).

Composition layer between the API route / analysis package and the
deterministic `app.outcome` modules:

    journey      -> reconstruct (Part 3)
    evidence     -> collect (Part 4)
    consistency  -> evaluate (Part 4)
    outcome      -> decide(journey, integrity, evidence, consistency)

Returns None for unknown transaction ids (the route turns that into 404).
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.outcome.engine import decide
from app.outcome.models import OutcomeResult
from app.schemas.outcome import (
    ConfidenceAdjustment,
    OutcomeReason,
    OutcomeResponse,
    RuleTraceStep,
)
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence


def build_outcome(journey, integrity, evidence, consistency) -> OutcomeResult:
    """Pure: run the deterministic decision engine over loaded inputs."""
    return decide(journey, integrity, evidence, consistency)


def _outcome_schema(result: OutcomeResult) -> OutcomeResponse:
    return OutcomeResponse(
        transaction_id=result.transaction_id,
        outcome=result.outcome,
        confidence=result.confidence,
        primary_reason=_reason_schema(result.primary_reason),
        reasons=[_reason_schema(reason) for reason in result.reasons],
        supporting_evidence_ids=result.supporting_evidence_ids,
        supporting_event_ids=result.supporting_event_ids,
        blocking_evidence_ids=result.blocking_evidence_ids,
        consistency_status=result.consistency_status,
        evidence_completeness=result.evidence_completeness,
        rule_trace=[
            RuleTraceStep(
                rule_id=step.rule_id,
                name=step.name,
                priority=step.priority,
                outcome=step.outcome,
                applied=step.applied,
                note=step.note,
            )
            for step in result.rule_trace
        ],
        confidence_adjustments=[
            ConfidenceAdjustment(
                signal=adjustment.signal,
                delta=adjustment.delta,
                note=adjustment.note,
            )
            for adjustment in result.confidence_adjustments
        ],
    )


def _reason_schema(reason: OutcomeReason) -> OutcomeReason:
    return OutcomeReason(
        code=reason.code,
        message=reason.message,
        severity=reason.severity,
        rule_id=reason.rule_id,
        event_ids=reason.event_ids,
        evidence_ids=reason.evidence_ids,
    )


def get_outcome(session: Session, transaction_id: str) -> Optional[OutcomeResponse]:
    """Load + decide + map. None when the transaction is unknown."""
    payment_uuid = _resolve_transaction_id(transaction_id)
    if payment_uuid is None:
        return None
    result = journeys_service._reconstruct_all(session, transaction_id)
    if result is None:
        return None
    journey, integrity, _graph = result
    context = load_domain_context(session, payment_uuid)
    if context is None:
        return None
    evidence = build_evidence(journey, integrity, context)
    consistency = build_consistency(journey, context)
    return _outcome_schema(build_outcome(journey, integrity, evidence, consistency))


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None