"""Refund entity: money returned against a captured payment."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import RefundStatus
from app.models.base import TimestampMixin, enum_type, uuid_pk_column


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_refund_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        enum_type(RefundStatus, "refund_status", length=16),
        nullable=False,
        index=True,
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    payment: Mapped["Payment"] = relationship(back_populates="refunds")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Refund id={self.id} status={self.status!r} "
            f"payment={self.payment_id}>"
        )