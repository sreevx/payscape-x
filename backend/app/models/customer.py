"""Customer entity: the buyer on the other side of the transaction.

Part 2 expands Customer with `updated_at` and a `merchant_id` link so the
dataset stays multi-merchant capable.
"""

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, uuid_pk_column


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("merchants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Identifier used by the merchant's own systems.
    external_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")  # noqa: F821
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")  # noqa: F821
    messages: Mapped[list["CustomerMessage"]] = relationship(  # noqa: F821
        back_populates="customer"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} external_id={self.external_id!r}>"