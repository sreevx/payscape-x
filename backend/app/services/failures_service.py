"""Compound Failure Engine service (Part 6).

Composition layer between the API routes and the deterministic
`app.failures` modules. It loads the same pipeline the analysis package
uses (journey -> evidence -> consistency -> outcome) and then runs the
compound-failure analysis on top of it:

    journey      -> reconstruct (Part 3)
    evidence     -> collect (Part 4)
    consistency  -> evaluate (Part 4)
    outcome      -> decide (Part 5)
    failure      -> analyze (Part 6)

Returns None for unknown transaction ids (the routes turn that into 404).
The dataset list endpoint pre-filters candidates by the event markers the
outcome engine uses, so journeys that can never be FAILED are skipped —
the filter list mirrors `app/outcome/rules.py` and is asserted by tests.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import EventType
from app.failures.engine import analyze
from app.failures.models import CompoundFailureResult
from app.models import Order, ScenarioInstance, TransactionEvent
from app.schemas.failures import (
    ChainEdgeItem,
    CompoundFailureResponse,
    FailureListItem,
    FailureListResponse,
    FailureNodeItem,
    RootCauseItem,
)
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.outcome_service import build_outcome

# Event markers that can produce a FAILED business outcome (mirrors the
# Part 5 rule registry — journeys without any of these are skipped by the
# dataset scan).
FAILURE_MARKER_EVENT_TYPES = [
    EventType.PAYMENT_FAILED.value,
    EventType.ORDER_CANCELLED.value,
    EventType.ORDER_NOT_CONFIRMED.value,
    EventType.INVENTORY_OUT_OF_STOCK.value,
    EventType.NO_FULFILLMENT.value,
    EventType.FULFILLMENT_FAILED.value,
    EventType.DELIVERY_FAILED.value,
    EventType.DELIVERY_RETURNED.value,
]


def build_failure(journey, integrity, evidence, consistency, outcome) -> CompoundFailureResult:
    """Pure: run the deterministic compound-failure engine."""
    return analyze(journey, integrity, evidence, consistency, outcome)


def _node_item(node) -> FailureNodeItem:
    return FailureNodeItem(
        node_id=node.node_id,
        kind=node.kind,
        stage=node.stage,
        label=node.label,
        status=node.status,
        message=node.message,
        rule_id=node.rule_id,
        event_ids=node.event_ids,
        evidence_ids=node.evidence_ids,
        timestamp=node.timestamp,
        metadata=dict(node.metadata),
    )


def _failure_schema(result: CompoundFailureResult) -> CompoundFailureResponse:
    return CompoundFailureResponse(
        compound_failure_id=result.compound_failure_id,
        transaction_id=result.transaction_id,
        detected=result.detected,
        reason=result.reason,
        severity=result.severity,
        classification=result.classification,
        primary_failure=(
            _node_item(result.primary_failure)
            if result.primary_failure is not None
            else None
        ),
        failure_chain=[_node_item(node) for node in result.failure_chain],
        edges=[
            ChainEdgeItem(
                edge_id=edge.edge_id,
                source_node=edge.source_node,
                target_node=edge.target_node,
                relationship_type=edge.relationship_type,
                rule_id=edge.rule_id,
                reason=edge.reason,
            )
            for edge in result.edges
        ],
        root_causes=[
            RootCauseItem(
                root_cause_id=root.root_cause_id,
                kind=root.kind,
                label=root.label,
                stage=root.stage,
                explanation=root.explanation,
                rule_id=root.rule_id,
                event_ids=root.event_ids,
                evidence_ids=root.evidence_ids,
            )
            for root in result.root_causes
        ],
        confidence=result.confidence,
        event_ids=result.event_ids,
        evidence_ids=result.evidence_ids,
        metadata=dict(result.metadata),
    )


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None


def get_failure(session: Session, transaction_id: str) -> Optional[CompoundFailureResponse]:
    """Load + analyze + map. None when the transaction is unknown."""
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
    outcome = build_outcome(journey, integrity, evidence, consistency)
    return _failure_schema(build_failure(journey, integrity, evidence, consistency, outcome))


# ---------------------------------------------------------------------------
# Dataset list scan
# ---------------------------------------------------------------------------

def _load_instances(session: Session) -> dict[str, ScenarioInstance]:
    rows = list(session.scalars(select(ScenarioInstance)))
    return {
        str(instance.metadata_.get("payment_id", "")): instance
        for instance in rows
        if instance.metadata_.get("payment_id")
    }


def _other_payments_on_shortage_skus(
    session: Session, payment_uuid: uuid.UUID, skus: list[str]
) -> tuple[set[str], dict[str, list[str]]]:
    """Other payments whose OUT_OF_STOCK records share the same SKUs.

    Cheap deterministic scan over OUT_OF_STOCK rows only — used by both the
    list endpoint (scope) and the impact service (cohort membership).
    Returns (other payment ids, payment -> skus seen).
    """
    if not skus:
        return set(), {}
    wanted = set(skus)
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value
            )
        )
    )
    other_payments: set[str] = set()
    skus_by_payment: dict[str, list[str]] = {}
    for row in rows:
        if row.payment_id is None or str(row.payment_id) == str(payment_uuid):
            continue
        payload_sku = (row.payload or {}).get("product_sku")
        if not payload_sku or payload_sku not in wanted:
            continue
        other_payments.add(str(row.payment_id))
        seen = set(skus_by_payment.setdefault(str(row.payment_id), []))
        seen.add(str(payload_sku))
        skus_by_payment[str(row.payment_id)] = sorted(seen)
    return other_payments, skus_by_payment


def _shortage_skus_for(session: Session, payment_uuid: uuid.UUID) -> list[str]:
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value,
                TransactionEvent.payment_id == payment_uuid,
            )
        )
    )
    skus = {
        str(row.payload.get("product_sku"))
        for row in rows
        if row.payload.get("product_sku")
    }
    return sorted(skus)


def _list_scope(
    session: Session, payment_uuid: uuid.UUID
) -> tuple[str, int, list[str]]:
    """Cheap scope: MULTI_TRANSACTION when other payments share the shortage
    SKUs. Returns (scope, affected_total, shared_skus)."""
    skus = _shortage_skus_for(session, payment_uuid)
    if not skus:
        return "SINGLE_TRANSACTION", 1, []
    others, _ = _other_payments_on_shortage_skus(session, payment_uuid, skus)
    if others:
        return "MULTI_TRANSACTION", len(others) + 1, skus
    return "SINGLE_TRANSACTION", 1, skus


def list_failures(
    session: Session,
    limit: int,
    offset: int,
    severity: Optional[str] = None,
    failure_type: Optional[str] = None,
    outcome: Optional[str] = None,
    scope: Optional[str] = None,
) -> tuple[list[FailureListItem], int]:
    outcome_filter = outcome
    """Detected compound failures across the dataset (deterministic).

    Only payments carrying a FAILED-capable marker are deep-analyzed; the
    rest cannot be compound failures. The scan is bounded by the seeded
    dataset and documented as such — it is not an unbounded table scan.
    """
    instances = _load_instances(session)
    marker_payments = {
        str(payment_id)
        for payment_id in session.scalars(
            select(TransactionEvent.payment_id)
            .where(TransactionEvent.event_type.in_(FAILURE_MARKER_EVENT_TYPES))
            .distinct()
        )
    }

    def instance_key(instance: ScenarioInstance):
        return int(instance.metadata_.get("journey_index", 0))

    ordered_instances = sorted(
        (
            instance
            for instance in instances.values()
            if str(instance.metadata_.get("payment_id", "")) in marker_payments
        ),
        key=instance_key,
    )

    all_items: list[FailureListItem] = []
    for instance in ordered_instances:
        transaction_id = str(instance.metadata_["payment_id"])
        try:
            payment_uuid = uuid.UUID(transaction_id)
        except (ValueError, AttributeError):
            continue
        journey, integrity, _graph = journeys_service._reconstruct_all(
            session, transaction_id
        )
        if journey is None:
            continue
        context = load_domain_context(session, payment_uuid)
        if context is None:
            continue
        evidence = build_evidence(journey, integrity, context)
        consistency = build_consistency(journey, context)
        outcome = build_outcome(journey, integrity, evidence, consistency)
        if outcome.outcome != "FAILED":
            continue
        # All detected compound failures carry a FAILED outcome, so any
        # other outcome filter intentionally returns nothing.
        if outcome_filter and outcome_filter.upper() != "FAILED":
            continue
        failure = build_failure(journey, integrity, evidence, consistency, outcome)
        if not failure.detected:
            continue
        if severity and failure.severity != severity.upper():
            continue

        primary = failure.primary_failure
        primary_kind = primary.kind if primary is not None else None
        primary_label = primary.label if primary is not None else None
        if failure_type and primary_kind != failure_type.upper():
            continue

        scope_value, affected_total, shared_skus = _list_scope(session, payment_uuid)
        if scope and scope_value != scope.upper().replace("-", "_"):
            continue

        order = None
        if journey.order_id:
            try:
                order = session.get(Order, uuid.UUID(journey.order_id))
            except (ValueError, AttributeError):
                order = None
        all_items.append(
            FailureListItem(
                transaction_id=transaction_id,
                order_id=journey.order_id or "",
                external_order_id=order.external_order_id if order else "",
                scenario_type=instance.scenario_type.value,
                scenario_slug=str(instance.scenario_type.value).lower(),
                outcome=outcome.outcome,
                severity=failure.severity,
                classification=failure.classification,
                detected=True,
                primary_failure_kind=primary_kind,
                primary_failure_label=primary_label,
                root_cause_kinds=[root.kind for root in failure.root_causes],
                chain_length=len(failure.failure_chain),
                distinct_stages=sorted(
                    {node.stage for node in failure.failure_chain}
                ),
                confidence=failure.confidence,
                scope=scope_value,
                affected_transactions=affected_total,
                shared_skus=shared_skus if scope_value == "MULTI_TRANSACTION" else [],
            )
        )

    return all_items[offset:offset + limit], len(all_items)
