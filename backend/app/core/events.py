"""Centralized event-type registry.

Part 2 rule: event-type strings are NEVER scattered through the codebase.
Everything that writes or reads a unified TransactionEvent uses EventType.

Event types use one consistent UPPER_SNAKE convention. The members below
cover order, payment, webhook, inventory, fulfillment, delivery, customer
and refund events, plus a small set of SYSTEM snapshot markers that future
engines may consume (e.g. ORDER_NOT_CONFIRMED emitted when an SLA window
expires without confirmation).
"""

from enum import Enum


class EventType(str, Enum):
    """Every event type that may appear in the unified event stream."""

    # --- Order ------------------------------------------------------
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    # SYSTEM snapshot: confirmation SLA window expired without an event.
    ORDER_NOT_CONFIRMED = "ORDER_NOT_CONFIRMED"

    # --- Payment -----------------------------------------------------
    PAYMENT_CREATED = "PAYMENT_CREATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"

    # --- Webhook -----------------------------------------------------
    WEBHOOK_SENT = "WEBHOOK_SENT"
    WEBHOOK_RECEIVED = "WEBHOOK_RECEIVED"
    WEBHOOK_DELAYED = "WEBHOOK_DELAYED"
    WEBHOOK_DUPLICATE = "WEBHOOK_DUPLICATE"
    WEBHOOK_PROCESSING_FAILED = "WEBHOOK_PROCESSING_FAILED"

    # --- Inventory ---------------------------------------------------
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    INVENTORY_RELEASED = "INVENTORY_RELEASED"
    INVENTORY_OUT_OF_STOCK = "INVENTORY_OUT_OF_STOCK"
    INVENTORY_RESERVATION_EXPIRED = "INVENTORY_RESERVATION_EXPIRED"
    INVENTORY_DECREMENTED = "INVENTORY_DECREMENTED"

    # --- Fulfillment -------------------------------------------------
    FULFILLMENT_CREATED = "FULFILLMENT_CREATED"
    FULFILLMENT_PROCESSING = "FULFILLMENT_PROCESSING"
    FULFILLMENT_PACKED = "FULFILLMENT_PACKED"
    FULFILLMENT_SHIPPED = "FULFILLMENT_SHIPPED"
    FULFILLMENT_FAILED = "FULFILLMENT_FAILED"
    # SYSTEM snapshot: fulfillment SLA window expired without fulfillment.
    NO_FULFILLMENT = "NO_FULFILLMENT"

    # --- Delivery ----------------------------------------------------
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    SHIPMENT_IN_TRANSIT = "SHIPMENT_IN_TRANSIT"
    DELIVERY_OUT_FOR_DELIVERY = "DELIVERY_OUT_FOR_DELIVERY"
    DELIVERY_COMPLETED = "DELIVERY_COMPLETED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    DELIVERY_RETURNED = "DELIVERY_RETURNED"

    # --- Customer ----------------------------------------------------
    CUSTOMER_MESSAGE_RECEIVED = "CUSTOMER_MESSAGE_RECEIVED"
    CUSTOMER_COMPLAINT = "CUSTOMER_COMPLAINT"

    # --- Refund ------------------------------------------------------
    REFUND_INITIATED = "REFUND_INITIATED"
    REFUND_COMPLETED = "REFUND_COMPLETED"
    REFUND_FAILED = "REFUND_FAILED"


# Human-readable grouping used by API docs and the frontend explorer.
EVENT_TYPE_GROUPS: dict[str, list[str]] = {
    "Order": [
        "ORDER_CREATED",
        "ORDER_CONFIRMED",
        "ORDER_CANCELLED",
        "ORDER_NOT_CONFIRMED",
    ],
    "Payment": [
        "PAYMENT_CREATED",
        "PAYMENT_AUTHORIZED",
        "PAYMENT_CAPTURED",
        "PAYMENT_FAILED",
        "PAYMENT_REFUNDED",
    ],
    "Webhook": [
        "WEBHOOK_SENT",
        "WEBHOOK_RECEIVED",
        "WEBHOOK_DELAYED",
        "WEBHOOK_DUPLICATE",
        "WEBHOOK_PROCESSING_FAILED",
    ],
    "Inventory": [
        "INVENTORY_RESERVED",
        "INVENTORY_RELEASED",
        "INVENTORY_OUT_OF_STOCK",
        "INVENTORY_RESERVATION_EXPIRED",
        "INVENTORY_DECREMENTED",
    ],
    "Fulfillment": [
        "FULFILLMENT_CREATED",
        "FULFILLMENT_PROCESSING",
        "FULFILLMENT_PACKED",
        "FULFILLMENT_SHIPPED",
        "FULFILLMENT_FAILED",
        "NO_FULFILLMENT",
    ],
    "Delivery": [
        "SHIPMENT_CREATED",
        "SHIPMENT_IN_TRANSIT",
        "DELIVERY_OUT_FOR_DELIVERY",
        "DELIVERY_COMPLETED",
        "DELIVERY_FAILED",
        "DELIVERY_RETURNED",
    ],
    "Customer": [
        "CUSTOMER_MESSAGE_RECEIVED",
        "CUSTOMER_COMPLAINT",
    ],
    "Refund": [
        "REFUND_INITIATED",
        "REFUND_COMPLETED",
        "REFUND_FAILED",
    ],
}

ALL_EVENT_TYPES: list[str] = [
    event_type
    for group in EVENT_TYPE_GROUPS.values()
    for event_type in group
]
