"""Decision Agent service (Part 8).

Composition layer between the API routes and the deterministic
`app.decision` modules. It loads the exact same Parts 3-7 pipeline the
analysis package uses (journey -> evidence -> consistency -> outcome ->
compound failure -> impact) plus the Part 7 simulation report, builds the
structured verified context, produces the decision (validated LLM proposal
or deterministic fallback) and persists it as an auditable, idempotent row.

Approval behaviour:

- GET generates the decision deterministically and upserts the row; the
  approval status of an existing row is NEVER reset.
- approve / reject only transition a PENDING row to APPROVED / REJECTED;
  transitions on a final row raise DecisionStateError (route -> 409).
- Approval records the merchant's decision only. Nothing here executes
  refunds, payments, messages or any external action.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    DecisionAction,
    DecisionApprovalStatus,
    DecisionSource,
)
from app.decision.engine import (
    configured_provider,
    decide_for_transaction,
)
from app.decision.llm import DecisionLLMProvider
from app.decision.models import APPROVAL_PENDING
from app.models import Decision
from app.schemas.decision import (
    AlternativeActionItem,
    DecisionResponse,
)
from app.services import simulation_service
from app.simulation.engine import simulate as run_simulation


class DecisionStateError(Exception):
    """Raised on an invalid approval transition (route -> HTTP 409)."""


def _resolve_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def _load_pipeline(session: Session, transaction_id: str):
    """Full Parts 3-7 pipeline + simulation report. None when unknown."""
    payment_uuid = _resolve_uuid(transaction_id)
    if payment_uuid is None:
        return None
    loaded = simulation_service._load_pipeline(session, transaction_id)
    if loaded is None:
        return None
    (journey, integrity, evidence, consistency, outcome, failure, impact,
     context, webhooks, cross, inventory_facts) = loaded
    report = run_simulation(
        journey, integrity, evidence, consistency, outcome, failure, impact,
        context, webhooks, cross, inventory_facts,
    )
    return journey, evidence, consistency, outcome, failure, impact, report


def _decision_row(
    session: Session, decision_id: uuid.UUID
) -> Optional[Decision]:
    return session.scalar(
        select(Decision).where(Decision.decision_id == decision_id)
    )


def _upsert_decision(
    session: Session,
    result,
    payment_uuid: uuid.UUID,
    note: Optional[str] = None,
) -> Decision:
    """Persist the deterministic decision (idempotent, keeps approval state)."""
    decision_uuid = uuid.UUID(result.decision_id)
    row = _decision_row(session, decision_uuid)
    now = datetime.now(timezone.utc)
    if row is None:
        row = Decision(
            decision_id=decision_uuid,
            transaction_id=payment_uuid,
            decision_source=DecisionSource(result.decision_source),
            recommended_action=DecisionAction(result.recommended_action),
            reason=result.reason,
            decision_confidence=result.decision_confidence,
            evidence_confidence=result.evidence_confidence,
            evidence_ids=result.evidence_ids,
            event_ids=result.event_ids,
            simulation_id=(
                uuid.UUID(result.simulation_id)
                if result.simulation_id is not None
                else None
            ),
            alternatives=[
                {"action": item.action, "reason": item.reason}
                for item in result.alternatives
            ],
            human_approval_required=result.human_approval_required,
            approval_status=DecisionApprovalStatus(APPROVAL_PENDING),
            rejection_reason=None,
            decided_at=None,
            metadata_=dict(result.metadata),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.decision_source = DecisionSource(result.decision_source)
        row.recommended_action = DecisionAction(result.recommended_action)
        row.reason = result.reason
        row.decision_confidence = result.decision_confidence
        row.evidence_confidence = result.evidence_confidence
        row.evidence_ids = result.evidence_ids
        row.event_ids = result.event_ids
        row.simulation_id = (
            uuid.UUID(result.simulation_id)
            if result.simulation_id is not None
            else None
        )
        row.alternatives = [
            {"action": item.action, "reason": item.reason}
            for item in result.alternatives
        ]
        row.human_approval_required = result.human_approval_required
        row.metadata_ = dict(result.metadata)
        row.updated_at = now
    if note:
        metadata = dict(row.metadata_ or {})
        metadata["request_note"] = note
        row.metadata_ = metadata
        row.updated_at = now
    session.commit()
    session.refresh(row)
    return row


def _response_schema(row: Decision) -> DecisionResponse:
    return DecisionResponse(
        decision_id=str(row.decision_id),
        transaction_id=str(row.transaction_id),
        decision_source=row.decision_source.value
        if hasattr(row.decision_source, "value") else str(row.decision_source),
        recommended_action=row.recommended_action.value
        if hasattr(row.recommended_action, "value") else str(row.recommended_action),
        reason=row.reason,
        decision_confidence=round(float(row.decision_confidence), 3),
        evidence_confidence=round(float(row.evidence_confidence), 3),
        evidence_ids=list(row.evidence_ids or []),
        event_ids=list(row.event_ids or []),
        simulation_id=str(row.simulation_id) if row.simulation_id else None,
        alternatives=[
            AlternativeActionItem(action=item["action"], reason=item["reason"])
            for item in (row.alternatives or [])
        ],
        human_approval_required=bool(row.human_approval_required),
        approval_status=row.approval_status.value
        if hasattr(row.approval_status, "value") else str(row.approval_status),
        rejection_reason=row.rejection_reason,
        decided_at=row.decided_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=dict(row.metadata_ or {}),
    )


def get_decision(
    session: Session,
    transaction_id: str,
    provider: Optional[DecisionLLMProvider] = None,
    provider_note: Optional[str] = None,
) -> Optional[DecisionResponse]:
    """Generate (idempotently persist) the decision. None when unknown."""
    payment_uuid = _resolve_uuid(transaction_id)
    if payment_uuid is None:
        return None
    loaded = _load_pipeline(session, transaction_id)
    if loaded is None:
        return None
    journey, evidence, consistency, outcome, failure, impact, report = loaded

    if provider is None:
        provider = configured_provider()
    result = decide_for_transaction(
        journey, evidence, consistency, outcome, failure, impact, report,
        provider=provider,
        provider_note=provider_note,
    )
    row = _upsert_decision(session, result, payment_uuid)
    return _response_schema(row)


def approve_decision(
    session: Session, decision_id: str, note: Optional[str] = None
) -> Optional[DecisionResponse]:
    """PENDING -> APPROVED. None when the decision does not exist."""
    decision_uuid = _resolve_uuid(decision_id)
    if decision_uuid is None:
        return None
    row = _decision_row(session, decision_uuid)
    if row is None:
        return None
    if row.approval_status != DecisionApprovalStatus.PENDING:
        raise DecisionStateError(
            f"Decision is already {row.approval_status.value}; only a "
            "PENDING decision can be approved."
        )
    row.approval_status = DecisionApprovalStatus.APPROVED
    row.decided_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    if note:
        metadata = dict(row.metadata_ or {})
        metadata["approval_note"] = note
        row.metadata_ = metadata
    session.commit()
    session.refresh(row)
    return _response_schema(row)


def reject_decision(
    session: Session, decision_id: str, reason: Optional[str] = None
) -> Optional[DecisionResponse]:
    """PENDING -> REJECTED. None when the decision does not exist."""
    decision_uuid = _resolve_uuid(decision_id)
    if decision_uuid is None:
        return None
    row = _decision_row(session, decision_uuid)
    if row is None:
        return None
    if row.approval_status != DecisionApprovalStatus.PENDING:
        raise DecisionStateError(
            f"Decision is already {row.approval_status.value}; only a "
            "PENDING decision can be rejected."
        )
    row.approval_status = DecisionApprovalStatus.REJECTED
    row.rejection_reason = reason
    row.decided_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(row)
    return _response_schema(row)