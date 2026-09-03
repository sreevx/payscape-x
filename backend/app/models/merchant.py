"""Merchant entity: the business that accepts payments.

Part 2 expands Merchant with `external_id`, `currency` and `timezone`.
"""

import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, uuid_pk_column


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Identifier the merchant uses in their own systems.
    external_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    # Default settlement currency and operational timezone.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="merchant")  # noqa: F821
    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")  # noqa: F821
    products: Mapped[list["Product"]] = relationship(back_populates="merchant")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Merchant id={self.id} name={self.name!r}>"