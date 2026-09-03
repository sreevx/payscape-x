"""Tests for the database layer: models, relationships, constraints, migrations.

The schema is portable: UUID keys, JSON payloads (JSONB on PostgreSQL) and
VARCHAR+CHECK enums, so the whole suite runs against in-memory SQLite while
production targets PostgreSQL.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.core.database import Base
from app.core.enums import (
    EventSource,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    ScenarioType,
    WebhookProcessingStatus,
)
from app.core.events import EventType
from app.models.customer import Customer
from app.models.customer_message import CustomerMessage
from app.models.fulfillment import Fulfillment, FulfillmentEvent
from app.models.inventory import InventoryRecord, Product
from app.models.merchant import Merchant
from app.models.order import Order
from app.models.payment import Payment
from app.models.refund import Refund
from app.models.scenario import ScenarioInstance
from app.models.shipment import DeliveryEvent, Shipment
from app.models.transaction_event import TransactionEvent
from app.models.webhook import Webhook

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Every business table the Part 2 schema models (alembic_version excluded).
EXPECTED_TABLES = {
    "merchants",
    "customers",
    "orders",
    "payments",
    "transaction_events",
    "webhooks",
    "products",
    "inventory_records",
    "inventory_events",
    "fulfillments",
    "fulfillment_events",
    "shipments",
    "delivery_events",
    "customer_messages",
    "refunds",
    "scenario_instances",
}


def test_expected_tables_and_columns_exist():
    tables = Base.metadata.tables
    assert EXPECTED_TABLES.issubset(set(tables))

    events = tables["transaction_events"]
    for column in (
        "id",
        "order_id",
        "payment_id",
        "event_type",
        "source",
        "timestamp",
        "correlation_id",
        "idempotency_key",
        "payload",
        "created_at",
        "ingestion_sequence",  # Part 3: authoritative ingestion order
    ):
        assert column in events.columns

    # Key indexes for journey replay and correlation lookups.
    index_names = {index.name for index in events.indexes}
    assert "ix_transaction_events_order_timestamp" in index_names
    assert "ix_transaction_events_correlation" in index_names
    assert "ix_transaction_events_ingestion_sequence" in index_names

    # Unique constraints that protect data integrity.
    payments = tables["payments"]
    unique_names = {constraint.name for constraint in payments.constraints}
    assert "uq_payments_provider_payment" in unique_names

    orders = tables["orders"]
    unique_names = {constraint.name for constraint in orders.constraints}
    assert "uq_orders_merchant_external" in unique_names

    instances = tables["scenario_instances"]
    instance_indexes = {index.name for index in instances.indexes}
    assert "ix_scenario_instances_correlation_id" in instance_indexes
    assert instances.c["correlation_id"].unique

    # Part 2 columns on the expanded entities.
    for table, column in (
        ("merchants", "external_id"),
        ("merchants", "timezone"),
        ("customers", "updated_at"),
        ("payments", "method"),
        ("payments", "captured_at"),
        ("webhooks", "provider_event_id"),
        ("webhooks", "processing_status"),
        ("shipments", "promised_delivery_at"),
    ):
        assert column in tables[table].columns, f"{table}.{column} missing"


def test_full_journey_persists_with_relationships(db_session_factory):
    session = db_session_factory()
    now = datetime.now(timezone.utc)

    merchant = Merchant(
        external_id="mer_novacart",
        name="NovaCart Commerce",
        currency="INR",
        timezone="Asia/Kolkata",
    )
    session.add(merchant)
    session.commit()

    customer = Customer(
        merchant_id=merchant.id,
        external_id="cus_nc_0001",
        name="Anika Gupta",
        email="anika.gupta.001@example.in",
    )
    session.add(customer)
    session.commit()

    order = Order(
        merchant_id=merchant.id,
        customer_id=customer.id,
        external_order_id="ORD-2026-1001",
        amount=Decimal("2499.0000"),
        currency="INR",
        status=OrderStatus.CREATED,
    )
    session.add(order)
    session.commit()

    payment = Payment(
        order_id=order.id,
        provider="razorpay",
        provider_payment_id="pay_test_0001",
        amount=order.amount,
        currency="INR",
        status=PaymentStatus.CAPTURED,
        method=PaymentMethod.UPI,
        captured_at=now,
    )
    session.add(payment)
    session.commit()

    correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, "payscape:test:journey")
    scenario = ScenarioInstance(
        correlation_id=correlation_id,
        scenario_type=ScenarioType.NORMAL_SUCCESS,
        description="test journey",
        metadata_={"journey_index": 0},
    )
    session.add(scenario)

    webhook = Webhook(
        payment_id=payment.id,
        provider="razorpay",
        event_type="payment.captured",
        provider_event_id="evt_test_0001",
        received_at=now + timedelta(minutes=5),
        signature_verified=True,
        payload={"provider_payment_id": "pay_test_0001"},
        processing_status=WebhookProcessingStatus.PROCESSED,
    )
    session.add(webhook)

    refund = Refund(
        payment_id=payment.id,
        provider_refund_id="rfnd_test_0001",
        amount=payment.amount,
        currency="INR",
        status=RefundStatus.COMPLETED,
        initiated_at=now + timedelta(hours=3),
        completed_at=now + timedelta(days=1),
    )
    session.add(refund)

    message = CustomerMessage(
        customer_id=customer.id,
        order_id=order.id,
        channel="CHAT",
        direction="INBOUND",
        message="Please cancel my order",
        timestamp=now + timedelta(hours=2),
        metadata_={"about": "cancel_request"},
    )
    session.add(message)

    fulfillment = Fulfillment(order_id=order.id, status="SHIPPED")
    session.add(fulfillment)
    session.commit()
    session.add(FulfillmentEvent(
        fulfillment_id=fulfillment.id,
        event_type="FULFILLMENT_SHIPPED",
        timestamp=now + timedelta(hours=1),
        payload={},
    ))
    shipment = Shipment(
        order_id=order.id,
        fulfillment_id=fulfillment.id,
        carrier="BlueDart",
        tracking_number="AWB0000000001",
        status="DELIVERED",
        promised_delivery_at=now + timedelta(days=2),
        actual_delivery_at=now + timedelta(days=1),
    )
    session.add(shipment)
    session.commit()
    session.add(DeliveryEvent(
        shipment_id=shipment.id,
        event_type="DELIVERED",
        timestamp=now + timedelta(days=1),
        payload={},
    ))

    event = TransactionEvent(
        order_id=order.id,
        payment_id=payment.id,
        event_type=EventType.PAYMENT_CAPTURED,
        source=EventSource.PAYMENT_PROVIDER,
        timestamp=now,
        correlation_id=correlation_id,
        idempotency_key="capture:evt_test_0001",
        payload={"amount": "2499.0000"},
    )
    session.add(event)
    session.commit()

    # All entities have generated ids.
    assert all(
        entity.id is not None
        for entity in (merchant, customer, order, payment, scenario,
                       webhook, refund, message, fulfillment, shipment, event)
    )

    # Relationship graph resolves.
    session.refresh(order)
    assert order.merchant.name == "NovaCart Commerce"
    assert order.customer.email == "anika.gupta.001@example.in"
    assert order.payments[0].provider_payment_id == "pay_test_0001"
    assert order.fulfillments[0].shipments[0].tracking_number == "AWB0000000001"
    assert order.messages[0].message.startswith("Please cancel")

    session.refresh(payment)
    assert payment.webhooks[0].provider_event_id == "evt_test_0001"
    assert payment.refunds[0].status == RefundStatus.COMPLETED

    session.refresh(scenario)
    assert scenario.metadata_["journey_index"] == 0

    # Event links payment and journey correlation.
    session.refresh(event)
    assert event.correlation_id == correlation_id
    assert event.idempotency_key == "capture:evt_test_0001"
    assert event.payload["amount"] == "2499.0000"
    session.close()


def test_unique_constraints_enforced(db_session_factory):
    session = db_session_factory()

    merchant = Merchant(external_id="mer_x", name="Merchant X", currency="INR",
                        timezone="UTC")
    session.add(merchant)
    session.commit()
    order = Order(merchant_id=merchant.id, customer_id=None,
                  external_order_id="ORD-1", amount=Decimal("10"), currency="INR",
                  status=OrderStatus.CREATED)
    # customer required — build one first
    customer = Customer(merchant_id=merchant.id, external_id="cus_x",
                        name="X", email="x@example.com")
    session.add(customer)
    session.commit()
    order.customer_id = customer.id
    session.add(order)
    session.commit()

    # Same merchant + same external order id must be rejected.
    session.add(Order(merchant_id=merchant.id, customer_id=customer.id,
                      external_order_id="ORD-1", amount=Decimal("5"),
                      currency="INR", status=OrderStatus.CREATED))
    try:
        session.commit()
        raise AssertionError("duplicate (merchant, external_order_id) accepted")
    except Exception:
        session.rollback()

    # Same provider payment id must be rejected.
    payment = Payment(order_id=order.id, provider="razorpay",
                      provider_payment_id="pay_dup", amount=Decimal("10"),
                      currency="INR", status=PaymentStatus.CAPTURED)
    session.add(payment)
    session.commit()
    session.add(Payment(order_id=order.id, provider="razorpay",
                        provider_payment_id="pay_dup", amount=Decimal("10"),
                        currency="INR", status=PaymentStatus.CREATED))
    try:
        session.commit()
        raise AssertionError("duplicate (provider, provider_payment_id) accepted")
    except Exception:
        session.rollback()

    # Duplicate scenario correlation must be rejected.
    correlation = uuid.uuid4()
    session.add(ScenarioInstance(correlation_id=correlation,
                                 scenario_type=ScenarioType.NORMAL_SUCCESS,
                                 description="a", metadata_={}))
    session.commit()
    session.add(ScenarioInstance(correlation_id=correlation,
                                 scenario_type=ScenarioType.NORMAL_SUCCESS,
                                 description="b", metadata_={}))
    try:
        session.commit()
        raise AssertionError("duplicate scenario correlation accepted")
    except Exception:
        session.rollback()

    session.close()


def test_migration_chain_applies_and_reverts(tmp_path, monkeypatch):
    """Alembic upgrade head then downgrade base must round-trip cleanly."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "migration_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    # Upgrade 0001 -> 0002 head.
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    transaction_columns = {
        column["name"] for column in inspector.get_columns("transaction_events")
    }
    assert {"order_id", "correlation_id", "payment_id"}.issubset(
        transaction_columns
    )
    engine.dispose()

    # Full downgrade removes every business table.
    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert EXPECTED_TABLES.isdisjoint(set(inspector.get_table_names()))
    engine.dispose()
