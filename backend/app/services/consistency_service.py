"""Consistency Engine service (Part 4).

Composition layer between the API route and the deterministic
`app.consistency` modules:

    journey      -> reconstruct (Part 3)
    evidence     -> collect (Part 4)
    consistency  -> evaluate(journey, context)

Returns None for unknown transaction ids (the route turns that into 404).
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.consistency.evaluator import evaluate
from app.consistency.models import ConsistencyResult as ConsistencyResultModel
from app.schemas.consistency import ConsistencyCheck, ConsistencyResult
from app.services import journeys_service
from app.services.domain_context import load_domain_context


def build_consistency(
    journey, context
) -> ConsistencyResultModel:
    """Pure: run the deterministic evaluator over loaded inputs."""
    return evaluate(journey, context)


def _result_schema(result: ConsistencyResultModel) -> ConsistencyResult:
    return ConsistencyResult(
        transaction_id=result.transaction_id,
        checks=[
            ConsistencyCheck(
                rule_id=check.rule_id,
                name=check.name,
                description=check.description,
                severity=check.severity,
                status=check.status,
                supporting_event_ids=check.supporting_event_ids,
                explanation=check.explanation,
            )
            for check in result.checks
        ],
        passed=result.passed,
        violations=result.violations,
        insufficient_evidence=result.insufficient_evidence,
        not_applicable=result.not_applicable,
        overall_integrity=result.overall_integrity,
    )


def get_consistency(
    session: Session, transaction_id: str
) -> Optional[ConsistencyResult]:
    """Load + evaluate + map. None when the transaction is unknown."""
    payment_uuid = _resolve_transaction_id(transaction_id)
    if payment_uuid is None:
        return None
    result = journeys_service._reconstruct_all(session, transaction_id)
    if result is None:
        return None
    journey, _integrity, _graph = result
    context = load_domain_context(session, payment_uuid)
    if context is None:
        return None
    return _result_schema(build_consistency(journey, context))


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None