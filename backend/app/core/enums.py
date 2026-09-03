"""Domain value enums shared by models, generator, API and tests.

All members use UPPER_SNAKE values equal to their names so SQLAlchemy
`Enum` storage is unambiguous and JSON payloads stay readable.
"""

from enum import Enum


class StrEnum(str, Enum):
    """str-Enum with UPPER_SNAKE values identical to member names."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"
    FULFILLING = "FULFILLING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class PaymentMethod(StrEnum):
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"


class WebhookProcessingStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    DELAYED = "DELAYED"


class InventoryEventType(StrEnum):
    STOCK_AVAILABLE = "STOCK_AVAILABLE"
    STOCK_RESERVED = "STOCK_RESERVED"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    STOCK_RELEASED = "STOCK_RELEASED"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    STOCK_DECREMENTED = "STOCK_DECREMENTED"


class FulfillmentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ShipmentStatus(StrEnum):
    CREATED = "CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETURNED = "RETURNED"


class DeliveryEventType(StrEnum):
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    CUSTOMER_UNAVAILABLE = "CUSTOMER_UNAVAILABLE"
    RETURN_INITIATED = "RETURN_INITIATED"
    RETURNED = "RETURNED"


class CustomerMessageChannel(StrEnum):
    EMAIL = "EMAIL"
    CHAT = "CHAT"
    SMS = "SMS"
    SUPPORT = "SUPPORT"


class CustomerMessageDirection(StrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class RefundStatus(StrEnum):
    INITIATED = "INITIATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventSource(StrEnum):
    """Source of a unified TransactionEvent."""

    PAYMENT_PROVIDER = "PAYMENT_PROVIDER"
    WEBHOOK = "WEBHOOK"
    ORDER_SERVICE = "ORDER_SERVICE"
    INVENTORY_SERVICE = "INVENTORY_SERVICE"
    FULFILLMENT_SERVICE = "FULFILLMENT_SERVICE"
    DELIVERY_SERVICE = "DELIVERY_SERVICE"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"


class DecisionSource(StrEnum):
    """Where a decision recommendation came from (Part 8)."""

    LLM = "LLM"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class DecisionAction(StrEnum):
    """The closed registry of recommended actions (Part 8).

    The Decision Agent may ONLY recommend one of these four actions — never
    an arbitrary string. Approval records the merchant's decision; it never
    executes the action.
    """

    DO_NOTHING = "DO_NOTHING"
    RECOVER_ROOT_CAUSE = "RECOVER_ROOT_CAUSE"
    REFUND_OR_CONTAIN = "REFUND_OR_CONTAIN"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class DecisionApprovalStatus(StrEnum):
    """Human-approval lifecycle of one decision (Part 8)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ScenarioType(StrEnum):
    NORMAL_SUCCESS = "NORMAL_SUCCESS"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    DUPLICATE_WEBHOOK = "DUPLICATE_WEBHOOK"
    DELAYED_WEBHOOK = "DELAYED_WEBHOOK"
    INVENTORY_FAILURE = "INVENTORY_FAILURE"
    DELIVERY_FAILURE = "DELIVERY_FAILURE"
    REFUND_FLOW = "REFUND_FLOW"
    MISSING_EVENT = "MISSING_EVENT"
    CONTRADICTORY_EVENT = "CONTRADICTORY_EVENT"
    COMPOUND_FAILURE = "COMPOUND_FAILURE"
