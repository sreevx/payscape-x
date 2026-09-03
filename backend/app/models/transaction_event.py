"""TransactionEvent entity — the unified chronological event backbone.

Part 2 expands the model so a single stream can carry every stage of a
journey:

    Customer Intent → Order → Payment → Webhook → Inventory →
    Fulfillment → Shipment → Delivery → Customer Message

Key design points:

- `order_id` is always set — every event belongs to one business order.
- `payment_id` is set when the event concerns a payment (null otherwise).
- `correlation_id` ties one journey together across all entities; future
  modules (evidence, consistency, outcome) reconstruct the journey from it.
- `idempotency_key` lets future ingestion detect duplicates (e.g. the same
  provider webhook delivered twice).

Part 2 only *stores* events. Journey reconstruction and duplicate detection
are later parts.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventType
from app.core.enums import EventSource
from app.models.base import CreatedAtMixin, enum_type, uuid_pk_column


class TransactionEvent(CreatedAtMixin, Base):
    __tablename__ = "transaction_events"
    __table_args__ = (
        # Primary access patterns: journey replay and correlation lookups.
        Index("ix_transaction_events_order_timestamp", "order_id", "timestamp"),
        Index("ix_transaction_events_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[EventType] = mapped_column(
        enum_type(EventType, "event_type", length=64), nullable=False, index=True
    )
    source: Mapped[EventSource] = mapped_column(
        enum_type(EventSource, "event_source", length=32), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # The business journey this event belongs to.
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, index=True
    )
    # Provider/webhook idempotency identity (duplicate detection later).
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    # Monotonic insertion sequence — the authoritative ingestion order.
    # Assigned at persist time (generator append order for synthetic data,
    # next-value assignment for real ingestion). Timestamps are never used
    # here, so timestamp order != ingestion order stays detectable.
    ingestion_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0", index=True
    )
    # Free-form structured payload. JSON on SQLite, JSONB on PostgreSQL.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    order: Mapped["Order"] = relationship()  # noqa: F821
    payment: Mapped["Payment | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<TransactionEvent id={self.id} type={self.event_type} "
            f"order={self.order_id}>"
        )