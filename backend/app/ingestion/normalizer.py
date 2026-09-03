"""Deterministic event normalization (Part 3).

Maps arbitrary provider/source spellings onto the centralized Part 2 event
registry (`app.core.events.EventType`, `app.core.enums.EventSource`). There
is exactly one registry; this module is the only translator.

Events whose type or source is not in the registry are PRESERVED and marked
UNKNOWN — never deleted, never silently dropped, never auto-classified.
"""

from app.core.events import EventType
from app.core.enums import EventSource
from app.ingestion.models import CanonicalEvent, IngestionStatus

# ---------------------------------------------------------------------------
# Spelling tables: canonical registry value -> accepted provider spellings.
# The canonical UPPER_SNAKE value itself is always accepted (identity).
# ---------------------------------------------------------------------------

_TYPE_ALIASES: dict[str, list[str]] = {
    # --- Order ---------------------------------------------------------
    EventType.ORDER_CREATED.value: ["order.created", "order_created"],
    EventType.ORDER_CONFIRMED.value: ["order.confirmed", "order_confirmed"],
    EventType.ORDER_CANCELLED.value: ["order.cancelled", "order_cancelled"],
    EventType.ORDER_NOT_CONFIRMED.value: [
        "order.not_confirmed", "order_not_confirmed", "confirmation_sla_expired",
    ],
    # --- Payment ---------------------------------------------------------
    EventType.PAYMENT_CREATED.value: ["payment.created", "payment_created"],
    EventType.PAYMENT_AUTHORIZED.value: ["payment.authorized", "payment_authorized"],
    EventType.PAYMENT_CAPTURED.value: ["payment.captured", "payment_captured"],
    EventType.PAYMENT_FAILED.value: ["payment.failed", "payment_failed"],
    EventType.PAYMENT_REFUNDED.value: ["payment.refunded", "payment_refunded"],
    # --- Webhook ---------------------------------------------------------
    EventType.WEBHOOK_SENT.value: ["webhook.sent", "webhook_sent"],
    EventType.WEBHOOK_RECEIVED.value: ["webhook.received", "webhook_received"],
    EventType.WEBHOOK_DELAYED.value: ["webhook.delayed", "webhook_delayed"],
    EventType.WEBHOOK_DUPLICATE.value: ["webhook.duplicate", "webhook_duplicate"],
    EventType.WEBHOOK_PROCESSING_FAILED.value: [
        "webhook.processing_failed", "webhook_processing_failed",
    ],
    # --- Inventory -----------------------------------------------------
    EventType.INVENTORY_RESERVED.value: [
        "inventory.reserved", "inventory_reserved", "stock_reserved",
    ],
    EventType.INVENTORY_RELEASED.value: [
        "inventory.released", "inventory_released", "stock_released",
    ],
    EventType.INVENTORY_OUT_OF_STOCK.value: [
        "inventory.out_of_stock", "inventory_out_of_stock", "out_of_stock",
    ],
    EventType.INVENTORY_RESERVATION_EXPIRED.value: [
        "inventory.reservation_expired", "inventory_reservation_expired",
        "reservation_expired",
    ],
    EventType.INVENTORY_DECREMENTED.value: [
        "inventory.decremented", "inventory_decremented", "stock_decremented",
    ],
    # --- Fulfillment -----------------------------------------------------
    EventType.FULFILLMENT_CREATED.value: ["fulfillment.created", "fulfillment_created"],
    EventType.FULFILLMENT_PROCESSING.value: [
        "fulfillment.processing", "fulfillment_processing",
    ],
    EventType.FULFILLMENT_PACKED.value: ["fulfillment.packed", "fulfillment_packed"],
    EventType.FULFILLMENT_SHIPPED.value: ["fulfillment.shipped", "fulfillment_shipped"],
    EventType.FULFILLMENT_FAILED.value: ["fulfillment.failed", "fulfillment_failed"],
    EventType.NO_FULFILLMENT.value: ["no_fulfillment", "no.fulfillment"],
    # --- Delivery -----------------------------------------------------
    EventType.SHIPMENT_CREATED.value: ["shipment.created", "shipment_created"],
    EventType.SHIPMENT_IN_TRANSIT.value: [
        "shipment.in_transit", "shipment_in_transit", "in_transit",
    ],
    EventType.DELIVERY_OUT_FOR_DELIVERY.value: [
        "delivery.out_for_delivery", "delivery_out_for_delivery", "out_for_delivery",
    ],
    EventType.DELIVERY_COMPLETED.value: [
        "delivery.completed", "delivery_completed", "delivered",
    ],
    EventType.DELIVERY_FAILED.value: [
        "delivery.failed", "delivery_failed", "delivery_failure",
    ],
    EventType.DELIVERY_RETURNED.value: [
        "delivery.returned", "delivery_returned", "returned",
    ],
    # --- Customer -----------------------------------------------------
    EventType.CUSTOMER_MESSAGE_RECEIVED.value: [
        "customer.message_received", "customer_message_received",
    ],
    EventType.CUSTOMER_COMPLAINT.value: ["customer.complaint", "customer_complaint"],
    # --- Refund -----------------------------------------------------
    # Razorpay spells refunds refund.created / refund.processed.
    EventType.REFUND_INITIATED.value: [
        "refund.initiated", "refund_initiated", "refund.created",
    ],
    EventType.REFUND_COMPLETED.value: [
        "refund.completed", "refund_completed", "refund.processed",
    ],
    EventType.REFUND_FAILED.value: ["refund.failed", "refund_failed"],
}

_SOURCE_ALIASES: dict[str, list[str]] = {
    EventSource.PAYMENT_PROVIDER.value: ["payment_provider", "provider", "razorpay"],
    EventSource.WEBHOOK.value: ["webhook"],
    EventSource.ORDER_SERVICE.value: ["order_service", "orders"],
    EventSource.INVENTORY_SERVICE.value: ["inventory_service", "inventory"],
    EventSource.FULFILLMENT_SERVICE.value: ["fulfillment_service", "fulfillment"],
    EventSource.DELIVERY_SERVICE.value: ["delivery_service", "delivery", "shipping"],
    EventSource.CUSTOMER.value: ["customer"],
    EventSource.SYSTEM.value: ["system"],
}


def _build_lookup(aliases: dict[str, list[str]]) -> dict[str, str]:
    """Canonical value -> {uppercased alias -> canonical}."""
    lookup: dict[str, str] = {}
    for canonical, spellings in aliases.items():
        for spelling in [canonical] + spellings:
            lookup[spelling.upper()] = canonical
    return lookup


# Normalization lookup tables (case-insensitive by design).
EVENT_TYPE_LOOKUP: dict[str, str] = _build_lookup(_TYPE_ALIASES)
SOURCE_LOOKUP: dict[str, str] = _build_lookup(_SOURCE_ALIASES)

# Every registry value, for explicit UNKNOWN marking.
KNOWN_EVENT_TYPES: set[str] = {event_type.value for event_type in EventType}
KNOWN_SOURCES: set[str] = {source.value for source in EventSource}


def normalize_event_type(raw: str) -> tuple[str, bool]:
    """Map a raw event type to its canonical registry value.

    Returns (canonical, is_unknown). When unknown, the raw value is returned
    unchanged so it is preserved — never mapped, never dropped.
    """
    if not isinstance(raw, str) or not raw.strip():
        return raw, True
    canonical = EVENT_TYPE_LOOKUP.get(raw.strip().upper())
    if canonical is None:
        return raw, True
    return canonical, False


def normalize_source(raw: str) -> tuple[str, bool]:
    """Map a raw source to its canonical registry value (see above)."""
    if not isinstance(raw, str) or not raw.strip():
        return raw, True
    canonical = SOURCE_LOOKUP.get(raw.strip().upper())
    if canonical is None:
        return raw, True
    return canonical, False


def normalize_event(event: CanonicalEvent) -> CanonicalEvent:
    """Normalize an event in place, marking it UNKNOWN when unmappable.

    The canonical registry value replaces the raw spelling; if the raw value
    cannot be mapped, `event_type`/`source` keep the raw value and
    `is_unknown` becomes True. The raw value therefore survives inside the
    canonical event — it is preserved, just explicitly unclassified.
    """
    canonical_type, unknown_type = normalize_event_type(event.event_type)
    canonical_source, unknown_source = normalize_source(event.source)
    event.event_type = canonical_type
    event.source = canonical_source
    event.is_unknown = unknown_type or unknown_source
    event.ingestion_status = (
        IngestionStatus.UNKNOWN if event.is_unknown else IngestionStatus.NORMALIZED
    )
    return event