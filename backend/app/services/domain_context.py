"""Domain context loader (Part 4).

Loads the payment's existing Part 2 domain records into a deterministic
`DomainContext` value object. The evidence and consistency engines consume
only this value object — they never touch the database and never depend on
ORM objects, which keeps them pure and deterministic.

No new tables are created; everything is computed from existing records.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.models import (
    DomainContext,
    RefundView,
    WebhookView,
)
from app.models import (
    CustomerMessage,
    DeliveryEvent,
    Fulfillment,
    FulfillmentEvent,
    InventoryEvent,
    Order,
    Payment,
    Refund,
    Shipment,
    Webhook,
)


def load_domain_context(
    session: Session, payment_id: uuid.UUID
) -> Optional[DomainContext]:
    """Load the domain facts for one payment, or None when unknown."""
    payment = session.get(Payment, payment_id)
    if payment is None:
        return None

    order = session.get(Order, payment.order_id)
    webhooks = list(
        session.scalars(select(Webhook).where(Webhook.payment_id == payment_id))
    )
    refunds = list(
        session.scalars(select(Refund).where(Refund.payment_id == payment_id))
    )

    context = DomainContext(
        payment_status=payment.status.value if payment.status is not None else None,
        payment_amount=payment.amount,
        payment_provider_payment_id=payment.provider_payment_id,
        order_status=order.status.value if order is not None else None,
        order_amount=order.amount if order is not None else None,
        webhooks=[
            WebhookView(
                id=str(hook.id),
                event_type=hook.event_type,
                processing_status=(
                    hook.processing_status.value
                    if hook.processing_status is not None
                    else ""
                ),
                provider_payment_id=(hook.payload or {}).get("provider_payment_id"),
            )
            for hook in webhooks
        ],
        refunds=[
            RefundView(
                id=str(refund.id),
                status=refund.status.value if refund.status is not None else "",
                amount=refund.amount,
            )
            for refund in refunds
        ],
    )

    if order is not None:
        inventory_rows = list(
            session.scalars(
                select(InventoryEvent).where(InventoryEvent.order_id == order.id)
            )
        )
        context.inventory_event_types = {
            row.event_type.value for row in inventory_rows
        }

        fulfillments = list(
            session.scalars(
                select(Fulfillment).where(Fulfillment.order_id == order.id)
            )
        )
        context.fulfillment_statuses = [
            fulfillment.status.value for fulfillment in fulfillments
        ]
        if fulfillments:
            fulfillment_ids = [fulfillment.id for fulfillment in fulfillments]
            fulfillment_event_rows = list(
                session.scalars(
                    select(FulfillmentEvent).where(
                        FulfillmentEvent.fulfillment_id.in_(fulfillment_ids)
                    )
                )
            )
            context.fulfillment_event_types = {
                row.event_type for row in fulfillment_event_rows
            }

        shipments = list(
            session.scalars(
                select(Shipment).where(Shipment.order_id == order.id)
            )
        )
        context.shipment_statuses = [shipment.status.value for shipment in shipments]
        if shipments:
            shipment_ids = [shipment.id for shipment in shipments]
            delivery_rows = list(
                session.scalars(
                    select(DeliveryEvent).where(
                        DeliveryEvent.shipment_id.in_(shipment_ids)
                    )
                )
            )
            context.delivery_event_types = {
                row.event_type.value for row in delivery_rows
            }

        context.message_count = len(
            list(
                session.scalars(
                    select(CustomerMessage).where(
                        CustomerMessage.order_id == order.id
                    )
                )
            )
        )

    return context