"""Order entity: the commercial intent a payment is supposed to deliver.

Status follows the business lifecycle (CREATED → PAYMENT_PENDING →
CONFIRMED → FULFILLING → SHIPPED → DELIVERED, or CANCELLED / REFUNDED).
State-transition *intelligence* belongs to the future Consistency Engine —
the model only stores the state.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import OrderStatus
from app.models.base import TimestampMixin, enum_type, uuid_pk_column


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        # One merchant must never reuse the same external order id.
        UniqueConstraint(
            "merchant_id", "external_order_id", name="uq_orders_merchant_external"
        ),
        Index("ix_orders_merchant_created", "merchant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        enum_type(OrderStatus, "order_status"), nullable=False, index=True
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="orders")  # noqa: F821
    customer: Mapped["Customer"] = relationship(back_populates="orders")  # noqa: F821
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")  # noqa: F821
    fulfillments: Mapped[list["Fulfillment"]] = relationship(  # noqa: F821
        back_populates="order"
    )
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="order")  # noqa: F821
    messages: Mapped[list["CustomerMessage"]] = relationship(  # noqa: F821
        back_populates="order"
    )
    inventory_events: Mapped[list["InventoryEvent"]] = relationship(  # noqa: F821
        back_populates="order"
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} external={self.external_order_id!r}>"