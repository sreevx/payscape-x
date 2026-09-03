"""CustomerMessage entity.

Stores inbound/outbound communication around an order. The Intent Agent
(later part) will consume these; Part 2 only stores them.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import CustomerMessageChannel, CustomerMessageDirection
from app.models.base import CreatedAtMixin, enum_type, uuid_pk_column


class CustomerMessage(CreatedAtMixin, Base):
    __tablename__ = "customer_messages"
    __table_args__ = (
        Index("ix_customer_messages_order_timestamp", "order_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[CustomerMessageChannel] = mapped_column(
        enum_type(CustomerMessageChannel, "customer_message_channel", length=16),
        nullable=False,
    )
    direction: Mapped[CustomerMessageDirection] = mapped_column(
        enum_type(CustomerMessageDirection, "customer_message_direction", length=16),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # JSON on SQLite, JSONB on PostgreSQL.
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    customer: Mapped["Customer"] = relationship(back_populates="messages")  # noqa: F821
    order: Mapped["Order"] = relationship(back_populates="messages")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<CustomerMessage id={self.id} channel={self.channel.value} "
            f"direction={self.direction.value} order={self.order_id}>"
        )