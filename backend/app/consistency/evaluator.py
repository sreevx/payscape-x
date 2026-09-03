"""Consistency evaluation (Part 4).

Runs every rule in the registry against the reconstructed journey and the
evidence-backed domain facts, then aggregates the deterministic result.

overall_integrity semantics (documented in docs/architecture.md):

- any VIOLATION                      -> INCONSISTENT
- no violations, at least one PASS   -> CONSISTENT
- no violations, no PASS             -> INSUFFICIENT_EVIDENCE

overall_integrity is record agreement only — it is NOT the business outcome.
"""

from app.consistency.models import (
    ConsistencyCheck,
    ConsistencyResult,
    STATUS_PASS,
    STATUS_VIOLATION,
)
from app.consistency.rules import CONSISTENCY_RULES, EvaluatorInput
from app.evidence.models import DomainContext
from app.journey.reconstructor import ReconstructedJourney


def evaluate(
    journey: ReconstructedJourney, context: DomainContext
) -> ConsistencyResult:
    """Evaluate all rules deterministically for one journey."""
    by_type: dict[str, list] = {}
    for event in journey.chronological_events:
        by_type.setdefault(event.event_type, []).append(event)

    data = EvaluatorInput(journey=journey, context=context, by_type=by_type)

    result = ConsistencyResult(transaction_id=journey.transaction_id)
    for rule in CONSISTENCY_RULES:
        outcome = rule.evaluate(data)
        result.checks.append(
            ConsistencyCheck(
                rule_id=rule.rule_id,
                name=rule.name,
                description=rule.description,
                severity=rule.severity,
                status=outcome.status,
                supporting_event_ids=outcome.supporting_event_ids,
                explanation=outcome.explanation,
            )
        )
    return result