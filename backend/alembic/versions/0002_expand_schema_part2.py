"""part 2: expand core entities + journey domain tables + unified event stream

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.JSON:
    """JSON column — JSONB on PostgreSQL, JSON everywhere else."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Expand merchants
    # ---------------------------------------------------------------
    op.add_column(
        "merchants",
        sa.Column("external_id", sa.String(length=64), nullable=True),
    )
    op.add_column("merchants", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column(
        "merchants", sa.Column("timezone", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "ix_merchants_external_id", "merchants", ["external_id"], unique=True
    )

    # ---------------------------------------------------------------
    # Expand customers: merchant link + updated_at
    # (batch mode: plain ALTERs on PostgreSQL, copy-and-move on SQLite)
    # ---------------------------------------------------------------
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("merchant_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_customers_merchant_id_merchants",
            "merchants",
            ["merchant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_customers_merchant_id", ["merchant_id"])
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=_TS,
                nullable=False,
            )
        )

    # ---------------------------------------------------------------
    # Expand payments: method + captured_at
    # ---------------------------------------------------------------
    op.add_column("payments", sa.Column("method", sa.String(length=16), nullable=True))
    op.add_column(
        "payments", sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True)
    )

    # ---------------------------------------------------------------
    # Rebuild transaction_events (Part 1 shape -> unified stream shape)
    # ---------------------------------------------------------------
    op.drop_table("transaction_events")

    # ---------------------------------------------------------------
    # Products / inventory
    # ---------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_merchant_id", "products", ["merchant_id"])
    op.create_index(
        "ix_products_merchant_sku", "products", ["merchant_id", "sku"], unique=True
    )

    op.create_table(
        "inventory_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_records_product_id",
        "inventory_records",
        ["product_id"],
        unique=True,
    )

    op.create_table(
        "inventory_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_events_order_id", "inventory_events", ["order_id"]
    )
    op.create_index(
        "ix_inventory_events_order_timestamp",
        "inventory_events",
        ["order_id", "timestamp"],
    )
    op.create_index(
        "ix_inventory_events_product_id", "inventory_events", ["product_id"]
    )
    op.create_index(
        "ix_inventory_events_timestamp", "inventory_events", ["timestamp"]
    )

    # ---------------------------------------------------------------
    # Fulfillments
    # ---------------------------------------------------------------
    op.create_table(
        "fulfillments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fulfillments_order_id", "fulfillments", ["order_id"])
    op.create_index("ix_fulfillments_status", "fulfillments", ["status"])

    op.create_table(
        "fulfillment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fulfillment_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"], ["fulfillments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fulfillment_events_fulfillment_id",
        "fulfillment_events",
        ["fulfillment_id"],
    )
    op.create_index(
        "ix_fulfillment_events_fulfillment_timestamp",
        "fulfillment_events",
        ["fulfillment_id", "timestamp"],
    )
    op.create_index(
        "ix_fulfillment_events_timestamp", "fulfillment_events", ["timestamp"]
    )

    # ---------------------------------------------------------------
    # Shipments / delivery events
    # ---------------------------------------------------------------
    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("fulfillment_id", sa.Uuid(), nullable=True),
        sa.Column("carrier", sa.String(length=64), nullable=False),
        sa.Column("tracking_number", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("promised_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"], ["fulfillments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_fulfillment_id", "shipments", ["fulfillment_id"])
    op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])
    op.create_index("ix_shipments_status", "shipments", ["status"])

    op.create_table(
        "delivery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["shipment_id"], ["shipments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_events_shipment_id", "delivery_events", ["shipment_id"])
    op.create_index(
        "ix_delivery_events_shipment_timestamp",
        "delivery_events",
        ["shipment_id", "timestamp"],
    )
    op.create_index("ix_delivery_events_timestamp", "delivery_events", ["timestamp"])

    # ---------------------------------------------------------------
    # Webhooks (provider events about a payment)
    # ---------------------------------------------------------------
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("processing_status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_payment_id", "webhooks", ["payment_id"])
    op.create_index("ix_webhooks_provider_event_id", "webhooks", ["provider_event_id"])
    op.create_index("ix_webhooks_processing_status", "webhooks", ["processing_status"])

    # ---------------------------------------------------------------
    # Customer messages
    # ---------------------------------------------------------------
    op.create_table(
        "customer_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_messages_customer_id", "customer_messages", ["customer_id"]
    )
    op.create_index(
        "ix_customer_messages_order_id", "customer_messages", ["order_id"]
    )
    op.create_index(
        "ix_customer_messages_order_timestamp",
        "customer_messages",
        ["order_id", "timestamp"],
    )
    op.create_index(
        "ix_customer_messages_timestamp", "customer_messages", ["timestamp"]
    )

    # ---------------------------------------------------------------
    # Refunds
    # ---------------------------------------------------------------
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index("ix_refunds_provider_refund_id", "refunds", ["provider_refund_id"])
    op.create_index("ix_refunds_status", "refunds", ["status"])

    # ---------------------------------------------------------------
    # Scenario instances (journey traceability)
    # ---------------------------------------------------------------
    op.create_table(
        "scenario_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scenario_instances_correlation_id",
        "scenario_instances",
        ["correlation_id"],
        unique=True,
    )
    op.create_index(
        "ix_scenario_instances_scenario_type", "scenario_instances", ["scenario_type"]
    )

    # ---------------------------------------------------------------
    # Unified transaction event stream (rebuilt)
    # ---------------------------------------------------------------
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_events_correlation", "transaction_events", ["correlation_id"]
    )
    op.create_index(
        "ix_transaction_events_event_type", "transaction_events", ["event_type"]
    )
    op.create_index(
        "ix_transaction_events_order_id", "transaction_events", ["order_id"]
    )
    op.create_index(
        "ix_transaction_events_order_timestamp",
        "transaction_events",
        ["order_id", "timestamp"],
    )
    op.create_index(
        "ix_transaction_events_payment_id", "transaction_events", ["payment_id"]
    )
    op.create_index(
        "ix_transaction_events_timestamp", "transaction_events", ["timestamp"]
    )
    op.create_index(
        "ix_transaction_events_source", "transaction_events", ["source"]
    )
    op.create_index(
        "ix_transaction_events_idempotency_key",
        "transaction_events",
        ["idempotency_key"],
    )


def downgrade() -> None:
    # Drop the unified stream, then every new table, then undo column adds.
    op.drop_table("transaction_events")

    op.drop_table("scenario_instances")
    op.drop_table("refunds")
    op.drop_table("customer_messages")
    op.drop_table("webhooks")
    op.drop_table("delivery_events")
    op.drop_table("shipments")
    op.drop_table("fulfillment_events")
    op.drop_table("fulfillments")
    op.drop_table("inventory_events")
    op.drop_table("inventory_records")
    op.drop_table("products")

    op.drop_column("payments", "captured_at")
    op.drop_column("payments", "method")

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_index("ix_customers_merchant_id")
        batch_op.drop_constraint("fk_customers_merchant_id_merchants", type_="foreignkey")
        batch_op.drop_column("merchant_id")

    op.drop_index("ix_merchants_external_id", table_name="merchants")
    op.drop_column("merchants", "timezone")
    op.drop_column("merchants", "currency")
    op.drop_column("merchants", "external_id")

    # Recreate the Part 1 transaction_events shape.
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"], ["payments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_events_event_type", "transaction_events", ["event_type"]
    )
    op.create_index(
        "ix_transaction_events_timestamp", "transaction_events", ["timestamp"]
    )
    op.create_index(
        "ix_transaction_events_transaction_id",
        "transaction_events",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_events_tx_timestamp",
        "transaction_events",
        ["transaction_id", "timestamp"],
    )