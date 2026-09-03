"""Data-integrity validation for the synthetic dataset.

The validator checks STRUCTURAL properties only:

- foreign keys point at real rows
- amounts are consistent between order and payment
- timestamps parse and correlation ids exist
- no missing required fields

It deliberately does NOT check business-state correctness (e.g. it will not
say "DELIVERED before SHIPPED is invalid"). Contradiction detection belongs
to the future Consistency Engine — this validator must never flag a scenario
intentionally generated as contradictory, missing or delayed.
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    CustomerMessage,
    DeliveryEvent,
    Fulfillment,
    FulfillmentEvent,
    InventoryEvent,
    InventoryRecord,
    Merchant,
    Order,
    Payment,
    Product,
    Refund,
    ScenarioInstance,
    Shipment,
    TransactionEvent,
    Webhook,
)

logger = logging.getLogger(__name__)


def validate_dataset(session: Session) -> list[str]:
    """Run every structural check. Returns a list of problem descriptions.

    An empty list means the dataset is structurally sound.
    """
    problems: list[str] = []

    def exists(model, row_id, label: str, value) -> None:
        if row_id is None:
            problems.append(f"{label}: missing reference value ({value!r})")
            return
        found = session.get(model, row_id)
        if found is None:
            problems.append(f"{label}: {row_id} references a missing row ({value!r})")

    # --- referential integrity ---------------------------------------
    merchants = set(session.scalars(select(Merchant.id)).all())
    customers = set(session.scalars(select(Customer.id)).all())
    orders = set(session.scalars(select(Order.id)).all())
    payments = set(session.scalars(select(Payment.id)).all())
    products = set(session.scalars(select(Product.id)).all())
    fulfillments = set(session.scalars(select(Fulfillment.id)).all())
    shipments = set(session.scalars(select(Shipment.id)).all())
    scenario_correlations = set(
        session.scalars(select(ScenarioInstance.correlation_id)).all()
    )

    if len(merchants) != 1:
        problems.append(f"expected exactly 1 merchant, found {len(merchants)}")
    for merchant in session.scalars(select(Merchant)):
        if not merchant.external_id:
            problems.append(f"merchant {merchant.id} is missing external_id")

    for customer in session.scalars(select(Customer)):
        if customer.merchant_id not in merchants:
            problems.append(f"customer {customer.id} has invalid merchant_id")
        if not customer.email or "@" not in customer.email:
            problems.append(f"customer {customer.id} has an invalid email")

    for order in session.scalars(select(Order)):
        if order.merchant_id not in merchants:
            problems.append(f"order {order.id} has invalid merchant_id")
        if order.customer_id not in customers:
            problems.append(f"order {order.id} has invalid customer_id")
        if order.amount is None or order.amount < 0:
            problems.append(f"order {order.id} has an invalid amount")

    for payment in session.scalars(select(Payment)):
        if payment.order_id not in orders:
            problems.append(f"payment {payment.id} has invalid order_id")
        order = session.get(Order, payment.order_id) if payment.order_id in orders else None
        if order is not None and order.amount != payment.amount:
            problems.append(
                f"payment {payment.id} amount {payment.amount} does not match "
                f"its order ({order.amount})"
            )
        if payment.provider != "razorpay":
            problems.append(f"payment {payment.id} has unexpected provider")

    # --- webhooks ------------------------------------------------------
    for webhook in session.scalars(select(Webhook)):
        if webhook.payment_id not in payments:
            problems.append(f"webhook {webhook.id} has invalid payment_id")
        if webhook.received_at is None:
            problems.append(f"webhook {webhook.id} has no received_at")

    # --- inventory -----------------------------------------------------
    for record in session.scalars(select(InventoryRecord)):
        if record.product_id not in products:
            problems.append(f"inventory_record {record.id} has invalid product_id")
        if record.available_quantity < 0 or record.reserved_quantity < 0:
            problems.append(
                f"inventory_record {record.id} has negative quantity "
                f"({record.available_quantity}/{record.reserved_quantity})"
            )

    for event in session.scalars(select(InventoryEvent)):
        if event.order_id not in orders:
            problems.append(f"inventory_event {event.id} has invalid order_id")
        if event.product_id not in products:
            problems.append(f"inventory_event {event.id} has invalid product_id")

    # --- fulfillment ---------------------------------------------------
    for fulfillment in session.scalars(select(Fulfillment)):
        if fulfillment.order_id not in orders:
            problems.append(f"fulfillment {fulfillment.id} has invalid order_id")
    for event in session.scalars(select(FulfillmentEvent)):
        if event.fulfillment_id not in fulfillments:
            problems.append(f"fulfillment_event {event.id} has invalid fulfillment_id")

    # --- delivery ------------------------------------------------------
    for shipment in session.scalars(select(Shipment)):
        if shipment.order_id not in orders:
            problems.append(f"shipment {shipment.id} has invalid order_id")
        if shipment.fulfillment_id is not None and shipment.fulfillment_id not in fulfillments:
            problems.append(f"shipment {shipment.id} has invalid fulfillment_id")
        if not shipment.tracking_number:
            problems.append(f"shipment {shipment.id} has no tracking number")
    for event in session.scalars(select(DeliveryEvent)):
        if event.shipment_id not in shipments:
            problems.append(f"delivery_event {event.id} has invalid shipment_id")

    # --- messages / refunds ---------------------------------------------
    for message in session.scalars(select(CustomerMessage)):
        if message.customer_id not in customers:
            problems.append(f"customer_message {message.id} has invalid customer_id")
        if message.order_id not in orders:
            problems.append(f"customer_message {message.id} has invalid order_id")

    for refund in session.scalars(select(Refund)):
        if refund.payment_id not in payments:
            problems.append(f"refund {refund.id} has invalid payment_id")
        if refund.amount < 0:
            problems.append(f"refund {refund.id} has a negative amount")

    # --- unified event stream ------------------------------------------
    event_counts_by_order: Counter = Counter()
    for event in session.scalars(select(TransactionEvent)):
        if event.order_id not in orders:
            problems.append(f"transaction_event {event.id} has invalid order_id")
        if event.payment_id is not None and event.payment_id not in payments:
            problems.append(f"transaction_event {event.id} has invalid payment_id")
        if not isinstance(event.timestamp, datetime):
            problems.append(f"transaction_event {event.id} has an invalid timestamp")
        if event.correlation_id is None:
            problems.append(f"transaction_event {event.id} has no correlation_id")
        if event.correlation_id not in scenario_correlations:
            problems.append(
                f"transaction_event {event.id} correlation_id does not match any scenario"
            )
        if not isinstance(event.payload, dict):
            problems.append(f"transaction_event {event.id} payload is not an object")
        event_counts_by_order[str(event.order_id)] += 1

    # --- scenario instances ---------------------------------------------
    correlations: Counter = Counter()
    for instance in session.scalars(select(ScenarioInstance)):
        correlations[str(instance.correlation_id)] += 1
        if not isinstance(instance.metadata_, dict):
            problems.append(f"scenario_instance {instance.id} metadata is not an object")
    for correlation, count in correlations.items():
        if count > 1:
            problems.append(
                f"scenario correlation {correlation} appears {count} times"
            )

    # Every order should appear in the unified stream at least once.
    for order_id in orders:
        if event_counts_by_order.get(str(order_id), 0) == 0:
            problems.append(f"order {order_id} has no unified events")

    # --- scale sanity ---------------------------------------------------
    counts: Counter = Counter()
    for model in (Order, Payment, Webhook, InventoryEvent, FulfillmentEvent,
                  DeliveryEvent, CustomerMessage, Refund, TransactionEvent):
        counts[model.__name__] = session.scalar(select(func.count()).select_from(model)) or 0
    if counts["Order"] < 100:
        problems.append(f"unexpectedly small dataset: {counts['Order']} orders")

    return problems


def print_validation_report(session: Session) -> tuple[int, list[str]]:
    """Run validation and print a human-readable report.

    Returns (problem_count, problems) so the CLI can set an exit code.
    """
    counts: Counter = Counter()
    for model in (Merchant, Customer, Product, Order, Payment, Webhook,
                  InventoryRecord, InventoryEvent, Fulfillment, FulfillmentEvent,
                  Shipment, DeliveryEvent, CustomerMessage, Refund,
                  TransactionEvent, ScenarioInstance):
        counts[model.__name__] = session.scalar(
            select(func.count()).select_from(model)
        ) or 0

    scenario_counts = defaultdict(int)
    for scenario_type, in session.execute(select(ScenarioInstance.scenario_type)):
        scenario_counts[scenario_type.value] += 1

    print("PAYSCAPE-X Data Validation")
    print("--------------------------")
    print(f"Merchants:            {counts['Merchant']}")
    print(f"Customers:            {counts['Customer']}")
    print(f"Products:             {counts['Product']}")
    print(f"Orders:               {counts['Order']}")
    print(f"Payments:             {counts['Payment']}")
    print(f"Webhooks:             {counts['Webhook']}")
    print(f"Inventory records:    {counts['InventoryRecord']}")
    print(f"Inventory events:     {counts['InventoryEvent']}")
    print(f"Fulfillments:         {counts['Fulfillment']}")
    print(f"Fulfillment events:   {counts['FulfillmentEvent']}")
    print(f"Shipments:            {counts['Shipment']}")
    print(f"Delivery events:      {counts['DeliveryEvent']}")
    print(f"Customer messages:    {counts['CustomerMessage']}")
    print(f"Refunds:              {counts['Refund']}")
    print(f"Transaction events:   {counts['TransactionEvent']}")
    print(f"Scenario instances:   {counts['ScenarioInstance']}")
    print()
    for scenario_type in sorted(scenario_counts):
        print(f"  {scenario_type}: {scenario_counts[scenario_type]}")

    problems = validate_dataset(session)
    print()
    if problems:
        print(f"INTEGRITY PROBLEMS FOUND: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("No integrity problems found.")
    return len(problems), problems