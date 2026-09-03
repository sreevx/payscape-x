"""Fulfillment domain: order processing until hand-off to a carrier."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import FulfillmentStatus
from app.models.base import CreatedAtMixin, TimestampMixin, enum_type, uuid_pk_column


class Fulfillment(TimestampMixin, Base):
    __tablename__ = "fulfillments"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[FulfillmentStatus] = mapped_column(
        enum_type(FulfillmentStatus, "fulfillment_status", length=16),
        nullable=False,
        default=FulfillmentStatus.PENDING,
        index=True,
    )

    order: Mapped["Order"] = relationship(back_populates="fulfillments")  # noqa: F821
    events: Mapped[list["FulfillmentEvent"]] = relationship(  # noqa: F821
        back_populates="fulfillment",
        cascade="all, delete-orphan",
    )
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="fulfillment")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Fulfillment id={self.id} order={self.order_id} status={self.status!r}>"


class FulfillmentEvent(CreatedAtMixin, Base):
    __tablename__ = "fulfillment_events"
    __table_args__ = (
        Index("ix_fulfillment_events_fulfillment_timestamp", "fulfillment_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    fulfillment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("fulfillments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # JSON on SQLite, JSONB on PostgreSQL.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    fulfillment: Mapped["Fulfillment"] = relationship(back_populates="events")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<FulfillmentEvent id={self.id} type={self.event_type} "
            f"fulfillment={self.fulfillment_id}>"
        )