"""Read queries for payment-level transactions (journey unit)."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    Merchant,
    Order,
    Payment,
    ScenarioInstance,
    TransactionEvent,
)
from app.schemas.transactions import (
    EventItem,
    TransactionDetailResponse,
    TransactionListItem,
)
from app.synthetic.scenarios import SCENARIO_BY_TYPE, definition_for


def _matched_scenario_types(value: Optional[str]) -> list[str] | None:
    """Resolve a scenario filter (slug or type value) to enum values."""
    if not value:
        return None
    definition = definition_for(value)
    if definition is None:
        return []
    return [definition.scenario_type.value]


def _payment_scenario(session: Session, payment_id: uuid.UUID):
    """ScenarioInstance attached to a payment (via its event correlation)."""
    return session.scalars(
        select(ScenarioInstance)
        .join(
            TransactionEvent,
            TransactionEvent.correlation_id == ScenarioInstance.correlation_id,
        )
        .where(TransactionEvent.payment_id == payment_id)
        .limit(1)
    ).first()


def list_transactions(
    session: Session,
    limit: int,
    offset: int,
    scenario: Optional[str] = None,
    payment_status: Optional[str] = None,
):
    """Paginated list of transactions with scenario + status filters."""
    scenario_types = _matched_scenario_types(scenario)
    if scenario_types == []:
        # Filter matches nothing.
        return [], 0

    base = (
        select(Payment.id)
        .join(TransactionEvent, TransactionEvent.payment_id == Payment.id)
        .join(
            ScenarioInstance,
            ScenarioInstance.correlation_id == TransactionEvent.correlation_id,
        )
        .distinct()
    )
    if scenario_types is not None:
        base = base.where(ScenarioInstance.scenario_type.in_(scenario_types))
    if payment_status:
        base = base.where(Payment.status == payment_status)

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = session.execute(
        select(Payment, Order, Customer, Merchant)
        .join(Order, Payment.order_id == Order.id)
        .join(Customer, Order.customer_id == Customer.id)
        .join(Merchant, Order.merchant_id == Merchant.id)
        .where(Payment.id.in_(base))
        .order_by(Payment.created_at.desc(), Payment.id)
        .offset(offset)
        .limit(limit)
    ).all()

    if not rows:
        return [], total

    # All per-row lookups below run as a handful of batched queries instead of
    # one round trip per row (2 x `limit` queries against a remote database is
    # the difference between a sub-second page and a request that blows past
    # the frontend's timeout). Results are identical: one event count and one
    # scenario instance per payment on the page.
    page_payment_ids = [payment.id for payment, *_ in rows]

    count_rows = session.execute(
        select(TransactionEvent.payment_id, func.count(TransactionEvent.id))
        .where(TransactionEvent.payment_id.in_(page_payment_ids))
        .group_by(TransactionEvent.payment_id)
    ).all()
    event_counts: dict[uuid.UUID, int] = {
        payment_id: count for payment_id, count in count_rows
    }

    # Each payment belongs to one journey (one correlation), so the first
    # event in timestamp/id order pins the correlation deterministically.
    correlation_rows = session.execute(
        select(TransactionEvent.payment_id, TransactionEvent.correlation_id)
        .where(TransactionEvent.payment_id.in_(page_payment_ids))
        .order_by(TransactionEvent.timestamp.asc(), TransactionEvent.id)
    ).all()
    payment_correlation: dict[uuid.UUID, uuid.UUID] = {}
    for payment_id, correlation_id in correlation_rows:
        payment_correlation.setdefault(payment_id, correlation_id)

    scenario_rows = session.scalars(
        select(ScenarioInstance).where(
            ScenarioInstance.correlation_id.in_(
                list(payment_correlation.values())
            )
        )
    ).all()
    scenario_by_correlation = {
        instance.correlation_id: instance for instance in scenario_rows
    }

    items = []
    for payment, order, customer, _merchant in rows:
        count = event_counts.get(payment.id, 0) or 0
        correlation_id = payment_correlation.get(payment.id)
        scenario_instance = (
            scenario_by_correlation.get(correlation_id)
            if correlation_id is not None
            else None
        )
        definition = (
            SCENARIO_BY_TYPE.get(scenario_instance.scenario_type)
            if scenario_instance
            else None
        )
        items.append(
            TransactionListItem(
                id=str(payment.id),
                order_id=str(order.id),
                external_order_id=order.external_order_id,
                customer_name=customer.name,
                customer_email=customer.email,
                amount=payment.amount,
                currency=payment.currency,
                payment_status=payment.status.value,
                provider=payment.provider,
                method=payment.method.value if payment.method else None,
                scenario_type=(
                    scenario_instance.scenario_type.value if scenario_instance else None
                ),
                scenario_slug=definition.slug if definition else None,
                event_count=count,
                created_at=payment.created_at,
            )
        )
    return items, total


def get_transaction(session: Session, transaction_id: str) -> Optional[TransactionDetailResponse]:
    """Full transaction view or None when the id is unknown/invalid."""
    try:
        payment_uuid = uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None

    payment = session.get(Payment, payment_uuid)
    if payment is None:
        return None

    order = session.get(Order, payment.order_id)
    customer = session.get(Customer, order.customer_id) if order else None
    merchant = session.get(Merchant, order.merchant_id) if order else None
    scenario_instance = _payment_scenario(session, payment.id)
    definition = (
        SCENARIO_BY_TYPE.get(scenario_instance.scenario_type)
        if scenario_instance
        else None
    )
    event_rows = session.scalars(
        select(TransactionEvent)
        .where(TransactionEvent.payment_id == payment.id)
        .order_by(TransactionEvent.timestamp.asc(), TransactionEvent.id)
    ).all()

    events = [
        EventItem(
            id=str(event.id),
            order_id=str(event.order_id),
            payment_id=str(event.payment_id) if event.payment_id else None,
            event_type=event.event_type.value,
            source=event.source.value,
            timestamp=event.timestamp,
            correlation_id=str(event.correlation_id),
            idempotency_key=event.idempotency_key,
            payload=event.payload,
            created_at=event.created_at,
        )
        for event in event_rows
    ]

    return TransactionDetailResponse(
        id=str(payment.id),
        order_id=str(order.id),
        external_order_id=order.external_order_id,
        customer_id=str(customer.id),
        customer_name=customer.name,
        customer_email=customer.email,
        merchant_name=merchant.name,
        amount=payment.amount,
        currency=payment.currency,
        order_status=order.status.value,
        payment_status=payment.status.value,
        provider=payment.provider,
        provider_payment_id=payment.provider_payment_id,
        method=payment.method.value if payment.method else None,
        captured_at=payment.captured_at,
        created_at=payment.created_at,
        scenario_type=(
            scenario_instance.scenario_type.value if scenario_instance else None
        ),
        scenario_slug=definition.slug if definition else None,
        scenario_description=(
            scenario_instance.description if scenario_instance else None
        ),
        events=events,
    )