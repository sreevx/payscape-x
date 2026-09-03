"""Consequence / Impact Engine service (Part 6).

Composition layer between the API routes and the deterministic
`app.impact` modules. It loads the full pipeline (journey -> evidence ->
consistency -> outcome -> compound failure) plus the deterministic
cross-transaction facts (which other payments hit OUT_OF_STOCK on the same
SKUs) and then runs the impact engine:

    impact = analyze(journey, integrity, evidence, consistency, outcome,
                     failure, cross)

Returns None for unknown transaction ids (the route turns that into 404).
Cross-transaction impact is computed ONLY from explicit shared identifiers
(product SKU on OUT_OF_STOCK records) — never from fuzzy matching.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import EventType
from app.impact.engine import analyze
from app.impact.models import (
    AffectedTransaction,
    ConsequenceItem,
    CrossTransactionView,
    ImpactResult,
    ScoreComponent,
)
from app.models import Order, Payment, ScenarioInstance, TransactionEvent
from app.schemas.impact import (
    AffectedTransactionItem,
    ConsequenceItem as ConsequenceItemSchema,
    ImpactResponse,
    ScoreComponentItem,
)
from app.services import journeys_service, outcome_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.failures_service import (
    _other_payments_on_shortage_skus,
    _shortage_skus_for,
    build_failure,
)
from app.services.outcome_service import build_outcome

# Outcome computation per cohort member is bounded — the seeded dataset is
# small, and this cap keeps a pathological dataset from becoming expensive.
MAX_AFFECTED_OUTCOME_COMPUTATIONS = 25


def build_impact(journey, integrity, evidence, consistency, outcome, failure,
                 cross: Optional[CrossTransactionView] = None) -> ImpactResult:
    """Pure: run the deterministic impact engine over loaded inputs."""
    return analyze(journey, integrity, evidence, consistency, outcome, failure, cross)


def load_cross_transaction(
    session: Session, payment_uuid: uuid.UUID
) -> Optional[CrossTransactionView]:
    """Load other transactions hit by the same SKU shortage (deterministic)."""
    skus = _shortage_skus_for(session, payment_uuid)
    if not skus:
        return None
    others_ids, skus_by_payment = _other_payments_on_shortage_skus(
        session, payment_uuid, skus
    )
    if not others_ids:
        return CrossTransactionView(shortage_skus=skus)

    payments = list(
        session.scalars(
            select(Payment).where(Payment.id.in_([uuid.UUID(item) for item in others_ids]))
        )
    )
    order_uuids = [payment.order_id for payment in payments if payment.order_id]
    orders = {
        str(order.id): order
        for order in session.scalars(select(Order).where(Order.id.in_(order_uuids)))
    }
    instance_rows = list(session.scalars(select(ScenarioInstance)))
    instance_by_payment = {
        str(instance.metadata_.get("payment_id", "")): instance
        for instance in instance_rows
        if instance.metadata_.get("payment_id")
    }

    affected: list[AffectedTransaction] = []
    for index, payment in enumerate(payments):
        other_id = str(payment.id)
        if index >= MAX_AFFECTED_OUTCOME_COMPUTATIONS:
            break
        instance = instance_by_payment.get(other_id)
        order = orders.get(str(payment.order_id))
        outcome = outcome_service.get_outcome(session, other_id)
        affected.append(
            AffectedTransaction(
                transaction_id=other_id,
                order_id=str(payment.order_id),
                external_order_id=order.external_order_id if order else "",
                scenario_type=(
                    instance.scenario_type.value if instance is not None else None
                ),
                scenario_slug=(
                    str(instance.scenario_type.value).lower()
                    if instance is not None
                    else None
                ),
                outcome=outcome.outcome if outcome is not None else None,
                product_skus=skus_by_payment.get(other_id, []),
                impact="OBSERVED",
            )
        )
    affected.sort(key=lambda item: item.transaction_id)
    return CrossTransactionView(shortage_skus=skus, others=affected)


def _consequence_schema(item: ConsequenceItem) -> ConsequenceItemSchema:
    return ConsequenceItemSchema(
        consequence_id=item.consequence_id,
        category=item.category,
        claim=item.claim,
        classification=item.classification,
        rule_id=item.rule_id,
        event_ids=item.event_ids,
        evidence_ids=item.evidence_ids,
        metadata=dict(item.metadata),
    )


def _impact_schema(result: ImpactResult) -> ImpactResponse:
    return ImpactResponse(
        impact_id=result.impact_id,
        transaction_id=result.transaction_id,
        scope=result.scope,
        affected_transactions=result.affected_transactions,
        affected_orders=result.affected_orders,
        affected_products=result.affected_products,
        observed_consequences=[
            _consequence_schema(item) for item in result.observed_consequences
        ],
        derived_consequences=[
            _consequence_schema(item) for item in result.derived_consequences
        ],
        potential_consequences=[
            _consequence_schema(item) for item in result.potential_consequences
        ],
        severity=result.severity,
        impact_score=result.impact_score,
        shared_skus=result.shared_skus,
        shared_failure_patterns=result.shared_failure_patterns,
        affected=[
            AffectedTransactionItem(
                transaction_id=item.transaction_id,
                order_id=item.order_id,
                external_order_id=item.external_order_id,
                scenario_type=item.scenario_type,
                scenario_slug=item.scenario_slug,
                outcome=item.outcome,
                product_skus=item.product_skus,
                impact=item.impact,
            )
            for item in result.affected
        ],
        score_components=[
            ScoreComponentItem(signal=item.signal, points=item.points, note=item.note)
            for item in result.score_components
        ],
        event_ids=result.event_ids,
        evidence_ids=result.evidence_ids,
        metadata=dict(result.metadata),
    )


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None


def get_impact(session: Session, transaction_id: str) -> Optional[ImpactResponse]:
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
    failure = build_failure(journey, integrity, evidence, consistency, outcome)
    cross = load_cross_transaction(session, payment_uuid)
    impact = build_impact(
        journey, integrity, evidence, consistency, outcome, failure, cross
    )
    return _impact_schema(impact)
