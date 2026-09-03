"""ORM models.

Importing this package registers every model on `Base.metadata`, which is
what Alembic uses to generate and apply migrations.

Part 2 models cover the full journey the future engines will consume:

  Merchant, Customer, Order, Payment, Webhook
  Product, InventoryRecord, InventoryEvent
  Fulfillment, FulfillmentEvent
  Shipment, DeliveryEvent
  CustomerMessage, Refund
  TransactionEvent (unified chronological stream)
  ScenarioInstance (journey → scenario traceability)

Part 8 adds the Decision entity (audit trail + human-approval record).
"""

from app.models.customer import Customer
from app.models.customer_message import CustomerMessage
from app.models.decision import Decision
from app.models.fulfillment import Fulfillment, FulfillmentEvent
from app.models.inventory import InventoryEvent, InventoryRecord, Product
from app.models.merchant import Merchant
from app.models.order import Order
from app.models.payment import Payment
from app.models.refund import Refund
from app.models.scenario import ScenarioInstance
from app.models.shipment import DeliveryEvent, Shipment
from app.models.transaction_event import TransactionEvent
from app.models.webhook import Webhook

__all__ = [
    "Customer",
    "CustomerMessage",
    "Decision",
    "DeliveryEvent",
    "Fulfillment",
    "FulfillmentEvent",
    "InventoryEvent",
    "InventoryRecord",
    "Merchant",
    "Order",
    "Payment",
    "Product",
    "Refund",
    "ScenarioInstance",
    "Shipment",
    "TransactionEvent",
    "Webhook",
]