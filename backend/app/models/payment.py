"""Payment entity: the money movement against an order.

Part 2 adds `method` and `captured_at` and switches statuses to the
lifecycle vocabulary (CREATED / AUTHORIZED / CAPTURED / FAILED / REFUNDED /
PARTIALLY_REFUNDED). The `provider` field keeps the model ready for a real
Razorpay integration without redesign.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import PaymentMethod, PaymentStatus
from app.models.base import TimestampMixin, enum_type, uuid_pk_column


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        # A provider payment id is unique per provider.
        UniqueConstraint(
            "provider", "provider_payment_id", name="uq_payments_provider_payment"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus, "payment_status"), nullable=False, index=True
    )
    method: Mapped[PaymentMethod | None] = mapped_column(
        enum_type(PaymentMethod, "payment_method", length=16), nullable=True
    )
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship(back_populates="payments")  # noqa: F821
    webhooks: Mapped[list["Webhook"]] = relationship(back_populates="payment")  # noqa: F821
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Payment id={self.id} provider={self.provider!r} status={self.status!r}>"