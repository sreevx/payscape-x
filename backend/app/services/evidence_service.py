"""Evidence Engine service (Part 4).

Composition layer between the API route and the deterministic
`app.evidence` modules:

    journey  -> reconstruct (Part 3)
    evidence -> collect(journey, integrity, context)

The collector itself is pure; this module loads the reconstructed journey
and the domain context, then maps the report onto the API schema. Returns
None for unknown transaction ids (the route turns that into 404).
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.evidence.collector import collect
from app.evidence.models import EvidenceReport as EvidenceReportModel
from app.schemas.evidence import (
    EvidenceContradictionItem,
    EvidenceGapItem,
    EvidenceItem,
    EvidenceReport,
)
from app.services import journeys_service
from app.services.domain_context import load_domain_context


def build_evidence(
    journey, integrity, context
) -> EvidenceReportModel:
    """Pure: run the deterministic collector over loaded inputs."""
    return collect(journey, integrity, context)


def _report_schema(report: EvidenceReportModel) -> EvidenceReport:
    return EvidenceReport(
        transaction_id=report.transaction_id,
        evidence=[
            EvidenceItem(
                evidence_id=item.evidence_id,
                category=item.category,
                claim=item.claim,
                event_ids=item.event_ids,
                source=item.source,
                timestamp=item.timestamp,
                supporting_data=item.supporting_data,
                strength=item.strength,
                rule_id=item.rule_id,
                confidence=item.confidence,
                contradictions=item.contradictions,
                metadata=item.metadata,
            )
            for item in report.evidence
        ],
        gaps=[
            EvidenceGapItem(
                event_type=gap.event_type,
                rule_id=gap.rule_id,
                note=gap.note,
            )
            for gap in report.gaps
        ],
        contradictions=[
            EvidenceContradictionItem(
                contradiction_id=contradiction.contradiction_id,
                type=contradiction.type,
                rule_id=contradiction.rule_id,
                event_ids=contradiction.event_ids,
                explanation=contradiction.explanation,
                severity=contradiction.severity,
            )
            for contradiction in report.contradictions
        ],
        strength_summary=report.strength_summary,
    )


def get_evidence(session: Session, transaction_id: str) -> Optional[EvidenceReport]:
    """Load + collect + map. None when the transaction is unknown."""
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
    report = build_evidence(journey, integrity, context)
    return _report_schema(report)


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None