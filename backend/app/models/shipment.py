"""Delivery domain: Shipment with carrier tracking plus DeliveryEvent
ledger entries."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import DeliveryEventType, ShipmentStatus
from app.models.base import CreatedAtMixin, TimestampMixin, enum_type, uuid_pk_column


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fulfillment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("fulfillments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    tracking_number: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        enum_type(ShipmentStatus, "shipment_status", length=16),
        nullable=False,
        default=ShipmentStatus.CREATED,
        index=True,
    )
    promised_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship(back_populates="shipments")  # noqa: F821
    fulfillment: Mapped["Fulfillment | None"] = relationship(  # noqa: F821
        back_populates="shipments"
    )
    events: Mapped[list["DeliveryEvent"]] = relationship(  # noqa: F821
        back_populates="shipment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Shipment id={self.id} carrier={self.carrier!r} status={self.status!r}>"


class DeliveryEvent(CreatedAtMixin, Base):
    __tablename__ = "delivery_events"
    __table_args__ = (
        Index("ix_delivery_events_shipment_timestamp", "shipment_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[DeliveryEventType] = mapped_column(
        enum_type(DeliveryEventType, "delivery_event_type", length=32),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # JSON on SQLite, JSONB on PostgreSQL.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    shipment: Mapped["Shipment"] = relationship(back_populates="events")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<DeliveryEvent id={self.id} type={self.event_type} "
            f"shipment={self.shipment_id}>"
        )