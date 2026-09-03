"""Webhook entity: a raw provider webhook delivery.

A webhook is an event about a payment — it is NOT the payment itself, and it
is deliberately never merged into Payment state. Keeping it separate lets
Part 3 detect duplicates, delays and processing failures against raw
provider records.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import WebhookProcessingStatus
from app.models.base import CreatedAtMixin, enum_type, uuid_pk_column


class Webhook(CreatedAtMixin, Base):
    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # Provider event type, e.g. "payment.captured".
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Provider-side event identity — identical for duplicated deliveries.
    provider_event_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Raw provider payload. JSON on SQLite, JSONB on PostgreSQL.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    processing_status: Mapped[WebhookProcessingStatus] = mapped_column(
        enum_type(WebhookProcessingStatus, "webhook_processing_status", length=16),
        nullable=False,
        default=WebhookProcessingStatus.RECEIVED,
        index=True,
    )

    payment: Mapped["Payment"] = relationship(back_populates="webhooks")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Webhook id={self.id} provider_event={self.provider_event_id!r}>"