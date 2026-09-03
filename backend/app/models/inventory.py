"""Inventory domain: Product catalogue, running InventoryRecord and
InventoryEvent ledger entries.

InventoryEvent stores the *event* (reserved / released / out-of-stock ...)
against a product and order; InventoryRecord holds the running quantity
state (available / reserved).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import InventoryEventType
from app.models.base import CreatedAtMixin, TimestampMixin, enum_type, uuid_pk_column


class Product(CreatedAtMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        # SKU is unique per merchant.
        Index("ix_products_merchant_sku", "merchant_id", "sku", unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

    merchant: Mapped["Merchant"] = relationship(back_populates="products")  # noqa: F821
    inventory_records: Mapped[list["InventoryRecord"]] = relationship(  # noqa: F821
        back_populates="product"
    )
    inventory_events: Mapped[list["InventoryEvent"]] = relationship(  # noqa: F821
        back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r}>"


class InventoryRecord(Base):
    __tablename__ = "inventory_records"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    available_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product: Mapped["Product"] = relationship(back_populates="inventory_records")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<InventoryRecord product={self.product_id} "
            f"available={self.available_quantity} reserved={self.reserved_quantity}>"
        )


class InventoryEvent(CreatedAtMixin, Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        Index("ix_inventory_events_order_timestamp", "order_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[InventoryEventType] = mapped_column(
        enum_type(InventoryEventType, "inventory_event_type", length=32),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # JSON on SQLite, JSONB on PostgreSQL.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    order: Mapped["Order"] = relationship(back_populates="inventory_events")  # noqa: F821
    product: Mapped["Product"] = relationship(back_populates="inventory_events")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<InventoryEvent id={self.id} type={self.event_type} "
            f"order={self.order_id} product={self.product_id}>"
        )