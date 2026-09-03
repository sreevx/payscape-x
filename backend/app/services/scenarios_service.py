"""Read queries for synthetic scenario definitions and their journeys."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, Payment, ScenarioInstance, TransactionEvent
from app.schemas.scenarios import (
    ScenarioDetailResponse,
    ScenarioSummary,
    ScenarioTransactionItem,
    TimelineEventItem,
)
from app.synthetic.scenarios import SCENARIO_BY_SLUG, SCENARIO_BY_TYPE, definition_for


def _correlations_for_type(
    session: Session, scenario_type_value: str
) -> list:
    return list(
        session.scalars(
            select(ScenarioInstance.correlation_id).where(
                ScenarioInstance.scenario_type == scenario_type_value
            )
        )
    )


def list_scenarios(session: Session) -> list[ScenarioSummary]:
    """All scenario definitions with transaction + event counts."""
    from app.synthetic.scenarios import SCENARIO_DEFINITIONS

    summaries = []
    for definition in SCENARIO_DEFINITIONS:
        count = (
            session.scalar(
                select(func.count()).select_from(ScenarioInstance).where(
                    ScenarioInstance.scenario_type == definition.scenario_type
                )
            )
            or 0
        )
        event_count = 0
        if count:
            event_count = (
                session.scalar(
                    select(func.count())
                    .select_from(TransactionEvent)
                    .join(
                        ScenarioInstance,
                        TransactionEvent.correlation_id
                        == ScenarioInstance.correlation_id,
                    )
                    .where(
                        ScenarioInstance.scenario_type
                        == definition.scenario_type
                    )
                )
                or 0
            )
        summaries.append(
            ScenarioSummary(
                scenario_id=definition.slug,
                scenario_type=definition.scenario_type.value,
                name=definition.name,
                description=definition.description,
                transaction_count=count,
                event_count=event_count,
            )
        )
    return summaries


def get_scenario(session: Session, scenario_id: str) -> Optional[ScenarioDetailResponse]:
    """Scenario detail with transactions, counts and a sample timeline."""
    definition = SCENARIO_BY_SLUG.get(scenario_id)
    if definition is None:
        definition = definition_for(scenario_id)
    if definition is None:
        return None

    correlations = _correlations_for_type(session, definition.scenario_type.value)
    correlation_ids = [correlation for correlation in correlations]

    # Transactions: payments whose events share one of these correlations.
    payments = list(
        session.scalars(
            select(Payment)
            .join(TransactionEvent, TransactionEvent.payment_id == Payment.id)
            .where(
                TransactionEvent.correlation_id.in_(correlation_ids)
                if correlation_ids
                else False
            )
            .distinct()
        )
    )
    transactions = []
    for payment in payments:
        order = session.get(Order, payment.order_id)
        customer = session.get(Customer, order.customer_id) if order else None
        transactions.append(
            ScenarioTransactionItem(
                id=str(payment.id),
                order_id=str(order.id),
                external_order_id=order.external_order_id,
                customer_name=customer.name if customer else "unknown",
                amount=payment.amount,
                currency=payment.currency,
                payment_status=payment.status.value,
                created_at=payment.created_at,
            )
        )

    total_events = 0
    timeline: list[TimelineEventItem] = []
    if correlation_ids:
        total_events = (
            session.scalar(
                select(func.count())
                .select_from(TransactionEvent)
                .where(TransactionEvent.correlation_id.in_(correlation_ids))
            )
            or 0
        )
        # Timeline of the earliest generated journey of this scenario type.
        first_instance = session.scalars(
            select(ScenarioInstance)
            .where(ScenarioInstance.scenario_type == definition.scenario_type)
            .order_by(ScenarioInstance.created_at.asc())
            .limit(1)
        ).first()
        if first_instance is not None:
            events = session.scalars(
                select(TransactionEvent)
                .where(
                    TransactionEvent.correlation_id
                    == first_instance.correlation_id
                )
                .order_by(TransactionEvent.timestamp.asc())
            )
            timeline = [
                TimelineEventItem(
                    event_type=event.event_type.value,
                    source=event.source.value,
                    timestamp=event.timestamp,
                    correlation_id=str(event.correlation_id),
                )
                for event in events
            ]

    return ScenarioDetailResponse(
        scenario_id=definition.slug,
        scenario_type=definition.scenario_type.value,
        name=definition.name,
        description=definition.description,
        correlation_count=len(correlations),
        event_count=total_events,
        transactions=transactions,
        timeline=timeline,
    )