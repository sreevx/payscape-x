"""Deterministic synthetic dataset generator.

Produces coherent business-transaction journeys for the ten scenario types.
Every journey:

- gets its own `correlation_id` (uuid5 of seed + journey index)
- produces matching domain records (order, payment, webhook, inventory,
  fulfillment, shipment, delivery, messages, refunds)
- produces unified TransactionEvent records for every meaningful step
- is recorded in a ScenarioInstance for traceability

Running the generator twice with the same seed yields identical output
(ids, timestamps, amounts, payloads included). No randomness beyond the
seeded RNG, and no AI reasoning of any kind.
"""

import random
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from app.core.enums import (
    CustomerMessageChannel,
    CustomerMessageDirection,
    DeliveryEventType,
    EventSource,
    FulfillmentStatus,
    InventoryEventType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    ScenarioType,
    ShipmentStatus,
    WebhookProcessingStatus,
)
from app.core.events import EventType
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
from app.synthetic import data as catalogue
from app.synthetic.scenarios import SCENARIO_DEFINITIONS

DEFAULT_SEED = 42
NAMESPACE = uuid.NAMESPACE_URL
# All journeys begin after this instant; dataset ends well before "today".
BASE_TS = datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone.utc)

METHODS = [PaymentMethod(method) for method, _ in catalogue.PAYMENT_METHODS]
METHOD_WEIGHTS = [weight for _, weight in catalogue.PAYMENT_METHODS]
ZERO_STOCK_INDEXES = set(catalogue.OUT_OF_STOCK_PRODUCT_INDEXES)

TYPE_LABEL = {
    PaymentMethod.UPI: "upi",
    PaymentMethod.CARD: "card",
    PaymentMethod.NETBANKING: "netbanking",
    PaymentMethod.WALLET: "wallet",
}


def _uuid5(seed: int, kind: str, index: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"payscape:{seed}:{kind}:{index}")


def _hex(seed: int, kind: str, index: int, length: int) -> str:
    return _uuid5(seed, kind, index).hex[:length]


@dataclass
class Journey:
    """State for building one synthetic journey."""

    seed: int
    index: int
    scenario_type: ScenarioType
    start_ts: datetime
    rng: random.Random
    merchant: Merchant
    customers: list[Customer]
    products: list[Product]
    stock: dict[str, dict[str, int]]  # product id -> {available, reserved}
    correlation_id: uuid.UUID
    external_order_id: str

    order: Optional[Order] = None
    payment: Optional[Payment] = None

    records: list = field(default_factory=list)
    unified: list = field(default_factory=list)
    inventory_records: list = field(default_factory=list)
    webhook_rows: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self._inventory_seq = 0
        self._webhook_seq = 0
        self._fulfillment_event_seq = 0
        self._delivery_event_seq = 0

    # ---- time -------------------------------------------------------
    def at(self, minutes: float) -> datetime:
        return self.start_ts + timedelta(minutes=minutes)

    # ---- selection --------------------------------------------------
    def pick_product(self, need_stock: bool = True) -> tuple[Product, int]:
        """Pick a product (optionally requiring sellable stock) + quantity."""
        quantity = self.rng.randint(1, 2)
        if need_stock:
            candidates = [
                product
                for product in self.products
                if self.stock[str(product.id)]["available"] >= quantity
            ]
            product = self.rng.choice(candidates or self.products)
        else:
            zero_stock = [
                product
                for product in self.products
                if self.stock[str(product.id)]["available"] < quantity
            ]
            product = self.rng.choice(zero_stock or self.products)
        return product, quantity

    # ---- unified stream ---------------------------------------------
    def unified_event(
        self,
        event_type: EventType,
        source: EventSource,
        minutes: float,
        payload: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> TransactionEvent:
        assert self.order is not None and self.payment is not None
        event = TransactionEvent(
            id=_uuid5(self.seed, f"evt:{self.index}", len(self.unified)),
            order_id=self.order.id,
            payment_id=self.payment.id,
            event_type=event_type,
            source=source,
            timestamp=self.at(minutes),
            correlation_id=self.correlation_id,
            idempotency_key=idempotency_key,
            payload=payload or {},
            # Authoritative ingestion order = append order (Part 3).
            ingestion_sequence=len(self.unified),
        )
        self.unified.append(event)
        return event

    # ---- inventory --------------------------------------------------
    def inventory_event(
        self,
        product: Product,
        event_type: InventoryEventType,
        minutes: float,
        quantity: int,
        unified_type: EventType,
        extra: Optional[dict] = None,
    ) -> None:
        assert self.order is not None
        state = self.stock[str(product.id)]
        self._inventory_seq += 1
        record = InventoryEvent(
            id=_uuid5(self.seed, f"inv:{self.index}", self._inventory_seq),
            order_id=self.order.id,
            product_id=product.id,
            event_type=event_type,
            quantity=quantity,
            timestamp=self.at(minutes),
            payload={
                "sku": product.sku,
                "available_after": state["available"],
                "reserved_after": state["reserved"],
                **(extra or {}),
            },
        )
        self.records.append(record)
        self.unified_event(
            unified_type,
            EventSource.INVENTORY_SERVICE,
            minutes,
            payload={
                "product_sku": product.sku,
                "quantity": quantity,
                **(extra or {}),
            },
        )

    def reserve(self, journey_minutes: float, force_out_of_stock: bool = False,
                product: Optional[Product] = None, quantity: Optional[int] = None
                ) -> tuple[Product, int]:
        """Reserve stock, or emit OUT_OF_STOCK when it is unavailable."""
        if product is None or quantity is None:
            product, quantity = self.pick_product(need_stock=not force_out_of_stock)
        state = self.stock[str(product.id)]
        if state["available"] >= quantity:
            state["available"] -= quantity
            state["reserved"] += quantity
            self.inventory_event(
                product, InventoryEventType.STOCK_RESERVED, journey_minutes,
                quantity, EventType.INVENTORY_RESERVED,
            )
        else:
            self.inventory_event(
                product, InventoryEventType.OUT_OF_STOCK, journey_minutes,
                quantity, EventType.INVENTORY_OUT_OF_STOCK,
                extra={"requested": quantity, "available_before": state["available"]},
            )
        return product, quantity

    def release(self, product: Product, quantity: int, minutes: float,
                expired: bool = False) -> None:
        state = self.stock[str(product.id)]
        state["reserved"] -= quantity
        state["available"] += quantity
        if expired:
            self.inventory_event(
                product, InventoryEventType.RESERVATION_EXPIRED, minutes, quantity,
                EventType.INVENTORY_RESERVATION_EXPIRED,
            )
        else:
            self.inventory_event(
                product, InventoryEventType.STOCK_RELEASED, minutes, quantity,
                EventType.INVENTORY_RELEASED,
            )

    def decrement(self, product: Product, quantity: int, minutes: float) -> None:
        state = self.stock[str(product.id)]
        state["reserved"] -= quantity
        self.inventory_event(
            product, InventoryEventType.STOCK_DECREMENTED, minutes, quantity,
            EventType.INVENTORY_DECREMENTED,
        )

    # ---- domain events ----------------------------------------------
    def fulfillment_event(self, fulfillment: Fulfillment, event_type: str,
                          minutes: float, payload: Optional[dict] = None) -> None:
        self._fulfillment_event_seq += 1
        self.records.append(
            FulfillmentEvent(
                id=_uuid5(self.seed, f"fe:{self.index}", self._fulfillment_event_seq),
                fulfillment_id=fulfillment.id,
                event_type=event_type,
                timestamp=self.at(minutes),
                payload=payload or {},
            )
        )

    def delivery_event(self, shipment: Shipment, event_type: DeliveryEventType,
                       minutes: float, payload: Optional[dict] = None) -> None:
        self._delivery_event_seq += 1
        self.records.append(
            DeliveryEvent(
                id=_uuid5(self.seed, f"de:{self.index}", self._delivery_event_seq),
                shipment_id=shipment.id,
                event_type=event_type,
                timestamp=self.at(minutes),
                payload=payload or {},
            )
        )

    # ---- webhooks ----------------------------------------------------
    def webhook_row(
        self,
        provider_event: str,
        provider_event_id: str,
        received_minutes: float,
        status: WebhookProcessingStatus,
        payload: dict,
    ) -> Webhook:
        assert self.payment is not None
        self._webhook_seq += 1
        hook = Webhook(
            id=_uuid5(self.seed, f"wh:{self.index}", self._webhook_seq),
            payment_id=self.payment.id,
            provider="razorpay",
            event_type=provider_event,
            provider_event_id=provider_event_id,
            received_at=self.at(received_minutes),
            delivered_at=self.at(received_minutes + 1),
            signature_verified=True,
            payload=payload,
            processing_status=status,
        )
        self.records.append(hook)
        self.webhook_rows.append(hook)
        return hook


@dataclass
class Dataset:
    """Everything generated for one seed, ready to persist."""

    seed: int
    merchant: Merchant
    customers: list = field(default_factory=list)
    products: list = field(default_factory=list)
    records: list = field(default_factory=list)
    unified: list = field(default_factory=list)
    inventory_records: list = field(default_factory=list)
    instances: list = field(default_factory=list)

    def entity_counts(self) -> dict[str, int]:
        """Counts by model class name for summary/tests."""
        counts: Counter = Counter(type(record).__name__ for record in self.records)
        counts["Customer"] = len(self.customers)
        counts["Product"] = len(self.products)
        counts["TransactionEvent"] = len(self.unified)
        counts["ScenarioInstance"] = len(self.instances)
        return dict(counts)

    def summarize(self) -> dict:
        scenario_counts: Counter = Counter(
            instance.scenario_type.value for instance in self.instances
        )
        return {
            "merchant": self.merchant.name,
            "customers": len(self.customers),
            "products": len(self.products),
            "orders": len(self.orders),
            "payments": len(self.payments),
            "transaction_events": len(self.unified),
            "scenario_counts": dict(scenario_counts),
        }

    @property
    def orders(self) -> list:
        return [record for record in self.records if isinstance(record, Order)]

    @property
    def payments(self) -> list:
        return [record for record in self.records if isinstance(record, Payment)]

    @property
    def journeys(self) -> list[tuple[ScenarioInstance, list, list]]:
        """ScenarioInstance -> (payment, unified events) for that journey."""
        by_correlation: dict = {}
        for instance in self.instances:
            by_correlation[instance.correlation_id] = (instance, [])
        for event in self.unified:
            by_correlation[event.correlation_id][1].append(event)
        return sorted(
            (
                (instance, events)
                for instance, events in by_correlation.values()
            ),
            key=lambda pair: pair[0].metadata_["journey_index"],
        )


class DatasetGenerator:
    """Builds a deterministic Dataset for a given seed."""

    def __init__(self, seed: int = DEFAULT_SEED):
        self.seed = seed

    # ------------------------------------------------------------------
    def generate(self) -> Dataset:
        rng = random.Random(self.seed)

        merchant = Merchant(
            id=_uuid5(self.seed, "merchant", 0),
            name=catalogue.SEED_MERCHANT["name"],
            external_id=catalogue.SEED_MERCHANT["external_id"],
            currency=catalogue.SEED_MERCHANT["currency"],
            timezone=catalogue.SEED_MERCHANT["timezone"],
        )
        dataset = Dataset(seed=self.seed, merchant=merchant)

        # Customers: 100 clearly synthetic identities.
        for customer_index in range(100):
            given = rng.choice(catalogue.GIVEN_NAMES)
            family = rng.choice(catalogue.FAMILY_NAMES)
            dataset.customers.append(
                Customer(
                    id=_uuid5(self.seed, "customer", customer_index),
                    merchant_id=merchant.id,
                    external_id=f"cus_nc_{customer_index:04d}",
                    name=f"{given} {family}",
                    email=(
                        f"{given.lower()}.{family.lower()}"
                        f".{customer_index:03d}@example.in"
                    ),
                )
            )

        # Products + opening stock.
        stock: dict[str, dict[str, int]] = {}
        for product_index, (product_name, unit_price) in enumerate(
            catalogue.PRODUCT_CATALOGUE
        ):
            product = Product(
                id=_uuid5(self.seed, "product", product_index),
                merchant_id=merchant.id,
                sku=f"NC-{product_index:04d}",
                name=product_name,
                unit_price=Decimal(str(unit_price)),
            )
            dataset.products.append(product)
            available = 0 if product_index in ZERO_STOCK_INDEXES else rng.randint(30, 90)
            stock[str(product.id)] = {"available": available, "reserved": 0}
            dataset.inventory_records.append(
                InventoryRecord(
                    id=_uuid5(self.seed, "invrec", product_index),
                    product_id=product.id,
                    available_quantity=available,
                    reserved_quantity=0,
                )
            )

        # Journeys in chronological order.
        journey_index = 0
        minute_cursor = 0
        for definition in SCENARIO_DEFINITIONS:
            for _ in range(definition.count):
                minute_cursor += rng.randint(60, 150)
                journey = Journey(
                    seed=self.seed,
                    index=journey_index,
                    scenario_type=definition.scenario_type,
                    start_ts=BASE_TS + timedelta(minutes=minute_cursor),
                    rng=rng,
                    merchant=merchant,
                    customers=dataset.customers,
                    products=dataset.products,
                    stock=stock,
                    correlation_id=_uuid5(self.seed, "journey", journey_index),
                    external_order_id=f"ORD-2026-{1000 + journey_index}",
                )
                journey_index += 1

                builder = getattr(self, f"_build_{definition.slug}")
                builder(journey)

                dataset.records.extend(journey.records)
                dataset.unified.extend(journey.unified)
                dataset.instances.append(
                    ScenarioInstance(
                        id=_uuid5(self.seed, "scenario", journey_index),
                        correlation_id=journey.correlation_id,
                        scenario_type=journey.scenario_type,
                        description=definition.description,
                        metadata_={
                            "seed": self.seed,
                            "journey_index": journey.index,
                            "merchant": merchant.external_id,
                            "order_id": str(journey.order.id),
                            "payment_id": str(journey.payment.id),
                        },
                    )
                )

        # Final inventory snapshots (update the single record per product).
        for product_index, product in enumerate(dataset.products):
            state = stock[str(product.id)]
            dataset.inventory_records[product_index].available_quantity = state[
                "available"
            ]
            dataset.inventory_records[product_index].reserved_quantity = state[
                "reserved"
            ]
        return dataset

    # ------------------------------------------------------------------
    # Plumbing shared by journeys
    # ------------------------------------------------------------------
    def _begin(self, journey: Journey) -> None:
        """Create the order + payment skeleton shared by every journey."""
        customer = journey.rng.choice(journey.customers)
        amount = self._order_value(journey)

        order = Order(
            id=_uuid5(journey.seed, f"order:{journey.index}", 0),
            merchant_id=journey.merchant.id,
            customer_id=customer.id,
            external_order_id=journey.external_order_id,
            amount=Decimal(amount),
            currency="INR",
            status=OrderStatus.CREATED,
        )
        journey.order = order
        journey.records.append(order)

        method = journey.rng.choices(METHODS, METHOD_WEIGHTS)[0]
        payment = Payment(
            id=_uuid5(journey.seed, f"payment:{journey.index}", 0),
            order_id=order.id,
            provider="razorpay",
            provider_payment_id=f"pay_{_hex(journey.seed, 'ppid', journey.index, 14)}",
            amount=order.amount,
            currency="INR",
            status=PaymentStatus.CREATED,
            method=method,
        )
        journey.payment = payment
        journey.records.append(payment)

        journey.unified_event(
            EventType.ORDER_CREATED, EventSource.ORDER_SERVICE, 0,
            payload={
                "external_order_id": order.external_order_id,
                "merchant": journey.merchant.external_id,
            },
        )
        journey.unified_event(
            EventType.PAYMENT_CREATED, EventSource.PAYMENT_PROVIDER, 2,
            payload={
                "provider": "razorpay",
                "provider_payment_id": payment.provider_payment_id,
                "method": TYPE_LABEL[method],
            },
        )
        journey.unified_event(
            EventType.PAYMENT_AUTHORIZED, EventSource.PAYMENT_PROVIDER, 4,
            payload={"provider_payment_id": payment.provider_payment_id},
        )

    def _order_value(self, journey: Journey) -> Decimal:
        """Order value built from 1-3 catalogue products (kept coherent)."""
        total = Decimal(0)
        for _ in range(journey.rng.randint(1, 3)):
            product = journey.rng.choice(journey.products)
            total += product.unit_price * journey.rng.randint(1, 2)
        return total

    def _capture(
        self,
        journey: Journey,
        capture_minutes: float = 8,
        webhook_delay_minutes: float = 4,
        webhook_status: WebhookProcessingStatus = WebhookProcessingStatus.PROCESSED,
        provider_event_id: Optional[str] = None,
        delay_flag_minutes: Optional[float] = None,
    ) -> None:
        """Capture the payment and deliver its provider webhook."""
        assert journey.order is not None and journey.payment is not None
        journey.payment.status = PaymentStatus.CAPTURED
        journey.payment.captured_at = journey.at(capture_minutes)
        provider_event_id = provider_event_id or f"evt_{_hex(journey.seed, 'whid', journey.index, 12)}"

        journey.unified_event(
            EventType.PAYMENT_CAPTURED, EventSource.PAYMENT_PROVIDER, capture_minutes,
            payload={
                "provider_payment_id": journey.payment.provider_payment_id,
                "amount": str(journey.payment.amount),
                "currency": journey.payment.currency,
            },
            idempotency_key=f"capture:{provider_event_id}",
        )
        journey.unified_event(
            EventType.WEBHOOK_SENT, EventSource.PAYMENT_PROVIDER, capture_minutes + 1,
            payload={"provider_event_id": provider_event_id},
        )
        journey.webhook_row(
            provider_event="payment.captured",
            provider_event_id=provider_event_id,
            received_minutes=capture_minutes + webhook_delay_minutes,
            status=webhook_status,
            payload={
                "provider": "razorpay",
                "event": "payment.captured",
                "provider_payment_id": journey.payment.provider_payment_id,
                "signature": "verified",
            },
        )
        journey.unified_event(
            EventType.WEBHOOK_RECEIVED, EventSource.WEBHOOK,
            capture_minutes + webhook_delay_minutes + 1,
            payload={"provider_event_id": provider_event_id, "provider": "razorpay"},
            idempotency_key=provider_event_id,
        )
        if delay_flag_minutes is not None:
            journey.unified_event(
                EventType.WEBHOOK_DELAYED, EventSource.SYSTEM, delay_flag_minutes,
                payload={"provider_event_id": provider_event_id,
                         "delay_minutes": int(webhook_delay_minutes)},
            )
        return provider_event_id

    # ------------------------------------------------------------------
    # SCENARIO 1 — NORMAL SUCCESS
    # ------------------------------------------------------------------
    def _build_normal_success(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING
        self._capture(journey)
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 14,
            payload={"external_order_id": journey.order.external_order_id},
        )

        product, quantity = journey.reserve(22)
        fulfillment = self._fulfill(journey, product, quantity)
        shipment = self._create_shipment(journey, fulfillment, 170)
        self._deliver_ok(journey, shipment, 210)

    def _fulfill(self, journey: Journey, product: Product, quantity: int,
                 first_minutes: float = 40) -> Fulfillment:
        """Fulfillment lifecycle PENDING → PROCESSING → PACKED → SHIPPED."""
        assert journey.order is not None
        fulfillment = Fulfillment(
            id=_uuid5(journey.seed, f"fulfillment:{journey.index}", 0),
            order_id=journey.order.id,
            status=FulfillmentStatus.PENDING,
        )
        journey.records.append(fulfillment)
        journey.fulfillment_event(fulfillment, "FULFILLMENT_CREATED", first_minutes)
        journey.unified_event(
            EventType.FULFILLMENT_CREATED, EventSource.FULFILLMENT_SERVICE,
            first_minutes, payload={"fulfillment_id": str(fulfillment.id)},
        )

        fulfillment.status = FulfillmentStatus.PROCESSING
        journey.fulfillment_event(fulfillment, "FULFILLMENT_PROCESSING", first_minutes + 30)
        journey.unified_event(
            EventType.FULFILLMENT_PROCESSING, EventSource.FULFILLMENT_SERVICE,
            first_minutes + 30,
        )

        fulfillment.status = FulfillmentStatus.PACKED
        journey.fulfillment_event(fulfillment, "FULFILLMENT_PACKED", first_minutes + 70)
        journey.unified_event(
            EventType.FULFILLMENT_PACKED, EventSource.FULFILLMENT_SERVICE,
            first_minutes + 70,
        )

        fulfillment.status = FulfillmentStatus.SHIPPED
        assert journey.order is not None
        journey.order.status = OrderStatus.FULFILLING
        journey.fulfillment_event(fulfillment, "FULFILLMENT_SHIPPED", first_minutes + 110)
        journey.unified_event(
            EventType.FULFILLMENT_SHIPPED, EventSource.FULFILLMENT_SERVICE,
            first_minutes + 110,
        )
        journey.decrement(product, quantity, first_minutes + 112)
        return fulfillment

    def _create_shipment(self, journey: Journey, fulfillment: Fulfillment,
                         minutes: float) -> Shipment:
        assert journey.order is not None
        carrier = journey.rng.choice(catalogue.CARRIERS)
        shipment = Shipment(
            id=_uuid5(journey.seed, f"shipment:{journey.index}", 0),
            order_id=journey.order.id,
            fulfillment_id=fulfillment.id,
            carrier=carrier,
            tracking_number=f"AWB{journey.rng.randint(10**10, 10**11 - 1)}",
            status=ShipmentStatus.CREATED,
            promised_delivery_at=journey.at(minutes + 24 * 60),
        )
        journey.records.append(shipment)
        journey.delivery_event(shipment, DeliveryEventType.SHIPMENT_CREATED, minutes)
        journey.unified_event(
            EventType.SHIPMENT_CREATED, EventSource.DELIVERY_SERVICE, minutes,
            payload={"carrier": carrier, "tracking_number": shipment.tracking_number},
        )
        return shipment

    def _deliver_ok(self, journey: Journey, shipment: Shipment,
                    first_minutes: float = 210, delivery_minutes: float = 1500) -> None:
        """Standard successful delivery segment."""
        assert journey.order is not None
        shipment.status = ShipmentStatus.IN_TRANSIT
        journey.delivery_event(shipment, DeliveryEventType.PICKED_UP, first_minutes)
        journey.delivery_event(shipment, DeliveryEventType.IN_TRANSIT, first_minutes + 40)
        journey.unified_event(
            EventType.SHIPMENT_IN_TRANSIT, EventSource.DELIVERY_SERVICE,
            first_minutes + 40,
        )

        shipment.status = ShipmentStatus.OUT_FOR_DELIVERY
        journey.delivery_event(
            shipment, DeliveryEventType.OUT_FOR_DELIVERY, delivery_minutes - 180
        )
        journey.unified_event(
            EventType.DELIVERY_OUT_FOR_DELIVERY, EventSource.DELIVERY_SERVICE,
            delivery_minutes - 180,
        )

        shipment.status = ShipmentStatus.DELIVERED
        shipment.actual_delivery_at = journey.at(delivery_minutes)
        journey.order.status = OrderStatus.DELIVERED
        journey.delivery_event(shipment, DeliveryEventType.DELIVERED, delivery_minutes)
        journey.unified_event(
            EventType.DELIVERY_COMPLETED, EventSource.DELIVERY_SERVICE,
            delivery_minutes,
            payload={"tracking_number": shipment.tracking_number},
        )

    # ------------------------------------------------------------------
    # SCENARIO 2 — PAYMENT FAILED
    # ------------------------------------------------------------------
    def _build_payment_failed(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None and journey.payment is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        journey.payment.status = PaymentStatus.FAILED
        journey.unified_event(
            EventType.PAYMENT_FAILED, EventSource.PAYMENT_PROVIDER, 10,
            payload={
                "provider_payment_id": journey.payment.provider_payment_id,
                "reason": "payment declined by issuer",
                "error_code": "BAD_REQUEST_ERROR",
            },
        )
        provider_event_id = f"evt_{_hex(journey.seed, 'failid', journey.index, 12)}"
        journey.webhook_row(
            provider_event="payment.failed",
            provider_event_id=provider_event_id,
            received_minutes=12,
            status=WebhookProcessingStatus.PROCESSED,
            payload={"provider": "razorpay", "event": "payment.failed",
                     "error_code": "BAD_REQUEST_ERROR"},
        )
        journey.unified_event(
            EventType.WEBHOOK_RECEIVED, EventSource.WEBHOOK, 14,
            payload={"provider_event_id": provider_event_id},
            idempotency_key=provider_event_id,
        )
        journey.order.status = OrderStatus.CANCELLED
        journey.unified_event(
            EventType.ORDER_CANCELLED, EventSource.ORDER_SERVICE, 20,
            payload={"reason": "payment_failed"},
        )

    # ------------------------------------------------------------------
    # SCENARIO 3 — DUPLICATE WEBHOOK
    # ------------------------------------------------------------------
    def _build_duplicate_webhook(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        provider_event_id = f"evt_{_hex(journey.seed, 'dup', journey.index, 12)}"
        self._capture(journey, provider_event_id=provider_event_id)

        # The same provider event arrives again — identical identity.
        journey.webhook_row(
            provider_event="payment.captured",
            provider_event_id=provider_event_id,
            received_minutes=20,
            status=WebhookProcessingStatus.DUPLICATE,
            payload={"provider": "razorpay", "event": "payment.captured",
                     "duplicate_of": provider_event_id},
        )
        journey.unified_event(
            EventType.WEBHOOK_DUPLICATE, EventSource.WEBHOOK, 21,
            payload={"provider_event_id": provider_event_id},
            idempotency_key=provider_event_id,
        )

        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 26,
        )
        product, quantity = journey.reserve(32)
        fulfillment = self._fulfill(journey, product, quantity, first_minutes=60)
        shipment = self._create_shipment(journey, fulfillment, 180)
        self._deliver_ok(journey, shipment, 220)

    # ------------------------------------------------------------------
    # SCENARIO 4 — DELAYED WEBHOOK
    # ------------------------------------------------------------------
    def _build_delayed_webhook(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        # Webhook is delayed ~8 hours after capture. It finally arrives and
        # the delay monitor flags it, then the order is confirmed.
        provider_event_id = self._capture(
            journey,
            webhook_delay_minutes=8 * 60 + 30,
            webhook_status=WebhookProcessingStatus.DELAYED,
        )
        journey.unified_event(
            EventType.WEBHOOK_DELAYED, EventSource.SYSTEM, 8 * 60 + 40,
            payload={"provider_event_id": provider_event_id,
                     "delay_minutes": 8 * 60 + 30},
        )
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 8 * 60 + 44,
            payload={"note": "confirmed after delayed webhook"},
        )
        product, quantity = journey.reserve(8 * 60 + 55)
        fulfillment = self._fulfill(journey, product, quantity,
                                    first_minutes=8 * 60 + 110)
        # Fulfillment is marked shipped at first_minutes + 110 (= 8h+220),
        # so the shipment must be created after that.
        shipment = self._create_shipment(journey, fulfillment, 8 * 60 + 230)
        self._deliver_ok(journey, shipment, 8 * 60 + 260, delivery_minutes=8 * 60 + 1500)

    # ------------------------------------------------------------------
    # SCENARIO 5 — PAYMENT SUCCESS + INVENTORY FAILURE
    # ------------------------------------------------------------------
    def _build_inventory_failure(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        self._capture(journey)
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 14,
        )
        product, quantity = journey.reserve(30, force_out_of_stock=True)
        journey.unified_event(
            EventType.NO_FULFILLMENT, EventSource.SYSTEM, 360,
            payload={
                "reason": "inventory_unavailable",
                "product_sku": product.sku,
            },
        )

    # ------------------------------------------------------------------
    # SCENARIO 6 — PAYMENT SUCCESS + DELIVERY FAILURE
    # ------------------------------------------------------------------
    def _build_delivery_failure(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        self._capture(journey)
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 14,
        )
        product, quantity = journey.reserve(22)
        fulfillment = self._fulfill(journey, product, quantity)
        shipment = self._create_shipment(journey, fulfillment, 170)

        shipment.status = ShipmentStatus.IN_TRANSIT
        journey.delivery_event(shipment, DeliveryEventType.PICKED_UP, 210)
        journey.delivery_event(shipment, DeliveryEventType.IN_TRANSIT, 250)
        journey.unified_event(
            EventType.SHIPMENT_IN_TRANSIT, EventSource.DELIVERY_SERVICE, 250,
        )

        # Delivery fails after several attempts.
        shipment.status = ShipmentStatus.FAILED
        journey.delivery_event(
            shipment, DeliveryEventType.DELIVERY_FAILED, 1300,
            payload={"reason": "shipment damaged in transit"},
        )
        journey.unified_event(
            EventType.DELIVERY_FAILED, EventSource.DELIVERY_SERVICE, 1300,
            payload={
                "tracking_number": shipment.tracking_number,
                "reason": "shipment damaged in transit",
            },
        )
        # Return flow.
        shipment.status = ShipmentStatus.RETURNED
        journey.delivery_event(
            shipment, DeliveryEventType.RETURN_INITIATED, 2900,
            payload={"note": "return initiated after failed delivery"},
        )
        journey.delivery_event(shipment, DeliveryEventType.RETURNED, 2950)
        journey.unified_event(
            EventType.DELIVERY_RETURNED, EventSource.DELIVERY_SERVICE, 2900,
            payload={"tracking_number": shipment.tracking_number},
        )
        journey.records.append(
            CustomerMessage(
                id=_uuid5(journey.seed, f"msg:{journey.index}", 0),
                customer_id=journey.order.customer_id,
                order_id=journey.order.id,
                channel=CustomerMessageChannel.SUPPORT,
                direction=CustomerMessageDirection.INBOUND,
                message=(
                    f"My order {journey.order.external_order_id} shows delivered "
                    "but I never received it. Please investigate."
                ),
                timestamp=journey.at(2960),
                metadata_={"about": "delivery_failure"},
            )
        )
        journey.unified_event(
            EventType.CUSTOMER_MESSAGE_RECEIVED, EventSource.CUSTOMER, 2960,
            payload={"channel": "SUPPORT", "about": "delivery_failure"},
        )

    # ------------------------------------------------------------------
    # SCENARIO 7 — REFUND FLOW
    # ------------------------------------------------------------------
    def _build_refund_flow(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None and journey.payment is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        self._capture(journey)
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 14,
        )
        # Customer asks to cancel after confirmation.
        journey.order.status = OrderStatus.CANCELLED
        journey.unified_event(
            EventType.ORDER_CANCELLED, EventSource.ORDER_SERVICE, 200,
            payload={"reason": "customer_requested_cancellation"},
        )
        journey.records.append(
            CustomerMessage(
                id=_uuid5(journey.seed, f"msg:{journey.index}", 0),
                customer_id=journey.order.customer_id,
                order_id=journey.order.id,
                channel=CustomerMessageChannel.CHAT,
                direction=CustomerMessageDirection.INBOUND,
                message=(
                    f"Please cancel order {journey.order.external_order_id} "
                    "and refund me."
                ),
                timestamp=journey.at(205),
                metadata_={"about": "cancel_request"},
            )
        )
        journey.unified_event(
            EventType.CUSTOMER_MESSAGE_RECEIVED, EventSource.CUSTOMER, 205,
            payload={"channel": "CHAT", "about": "cancel_request"},
        )

        journey.payment.status = PaymentStatus.REFUNDED
        refund = Refund(
            id=_uuid5(journey.seed, f"refund:{journey.index}", 0),
            payment_id=journey.payment.id,
            provider_refund_id=f"rfnd_{_hex(journey.seed, 'rfnd', journey.index, 12)}",
            amount=journey.payment.amount,
            currency="INR",
            status=RefundStatus.COMPLETED,
            initiated_at=journey.at(220),
            completed_at=journey.at(1500),
        )
        journey.records.append(refund)
        journey.unified_event(
            EventType.REFUND_INITIATED, EventSource.PAYMENT_PROVIDER, 225,
            payload={"provider_refund_id": refund.provider_refund_id,
                     "amount": str(refund.amount)},
        )
        provider_event_id = f"evt_{_hex(journey.seed, 'rfndwh', journey.index, 12)}"
        journey.webhook_row(
            provider_event="refund.processed",
            provider_event_id=provider_event_id,
            received_minutes=1490,
            status=WebhookProcessingStatus.PROCESSED,
            payload={"provider": "razorpay", "event": "refund.processed"},
        )
        journey.unified_event(
            EventType.WEBHOOK_RECEIVED, EventSource.WEBHOOK, 1491,
            payload={"provider_event_id": provider_event_id},
            idempotency_key=provider_event_id,
        )
        journey.unified_event(
            EventType.REFUND_COMPLETED, EventSource.PAYMENT_PROVIDER, 1500,
            payload={"provider_refund_id": refund.provider_refund_id,
                     "completed_at": refund.completed_at.isoformat()},
        )
        journey.unified_event(
            EventType.PAYMENT_REFUNDED, EventSource.PAYMENT_PROVIDER, 1502,
            payload={"provider_payment_id": journey.payment.provider_payment_id,
                     "amount": str(refund.amount)},
        )
        journey.order.status = OrderStatus.REFUNDED

    # ------------------------------------------------------------------
    # SCENARIO 8 — MISSING EVENT
    # ------------------------------------------------------------------
    def _build_missing_event(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None and journey.payment is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        # Payment captured, but NO provider webhook ever arrives.
        journey.payment.status = PaymentStatus.CAPTURED
        journey.payment.captured_at = journey.at(8)
        journey.unified_event(
            EventType.PAYMENT_CAPTURED, EventSource.PAYMENT_PROVIDER, 8,
            payload={"provider_payment_id": journey.payment.provider_payment_id,
                     "amount": str(journey.payment.amount)},
        )
        # Expected WEBHOOK_RECEIVED is deliberately omitted.

    # ------------------------------------------------------------------
    # SCENARIO 9 — CONTRADICTORY EVENT
    # ------------------------------------------------------------------
    def _build_contradictory_event(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None and journey.payment is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        self._capture(journey)
        journey.order.status = OrderStatus.CONFIRMED
        journey.unified_event(
            EventType.ORDER_CONFIRMED, EventSource.ORDER_SERVICE, 14,
        )
        # Contradiction: a captured payment later reports FAILED.
        journey.payment.status = PaymentStatus.FAILED
        journey.unified_event(
            EventType.PAYMENT_FAILED, EventSource.PAYMENT_PROVIDER, 1500,
            payload={
                "provider_payment_id": journey.payment.provider_payment_id,
                "reason": "processor declined settlement (contradictory)",
            },
        )
        provider_event_id = f"evt_{_hex(journey.seed, 'contra', journey.index, 12)}"
        journey.webhook_row(
            provider_event="payment.failed",
            provider_event_id=provider_event_id,
            received_minutes=1502,
            status=WebhookProcessingStatus.PROCESSED,
            payload={"provider": "razorpay", "event": "payment.failed"},
        )
        journey.unified_event(
            EventType.WEBHOOK_RECEIVED, EventSource.WEBHOOK, 1504,
            payload={"provider_event_id": provider_event_id},
            idempotency_key=provider_event_id,
        )

    # ------------------------------------------------------------------
    # SCENARIO 10 — COMPOUND FAILURE
    # ------------------------------------------------------------------
    def _build_compound_failure(self, journey: Journey) -> None:
        self._begin(journey)
        assert journey.order is not None and journey.payment is not None
        journey.order.status = OrderStatus.PAYMENT_PENDING

        # 1. Payment is captured; stock is reserved immediately to hold it.
        provider_event_id = f"evt_{_hex(journey.seed, 'whid', journey.index, 12)}"
        journey.payment.status = PaymentStatus.CAPTURED
        journey.payment.captured_at = journey.at(8)
        journey.unified_event(
            EventType.PAYMENT_CAPTURED, EventSource.PAYMENT_PROVIDER, 8,
            payload={
                "provider_payment_id": journey.payment.provider_payment_id,
                "amount": str(journey.payment.amount),
                "currency": journey.payment.currency,
            },
            idempotency_key=f"capture:{provider_event_id}",
        )
        journey.unified_event(
            EventType.WEBHOOK_SENT, EventSource.PAYMENT_PROVIDER, 9,
            payload={"provider_event_id": provider_event_id},
        )
        product, quantity = journey.reserve(40)

        # 2. The webhook finally arrives ~12h late; the delay monitor flags it.
        journey.webhook_row(
            provider_event="payment.captured",
            provider_event_id=provider_event_id,
            received_minutes=8 + 12 * 60,
            status=WebhookProcessingStatus.DELAYED,
            payload={
                "provider": "razorpay",
                "event": "payment.captured",
                "provider_payment_id": journey.payment.provider_payment_id,
                "signature": "verified",
            },
        )
        journey.unified_event(
            EventType.WEBHOOK_RECEIVED, EventSource.WEBHOOK, 8 + 12 * 60 + 1,
            payload={"provider_event_id": provider_event_id, "provider": "razorpay"},
            idempotency_key=provider_event_id,
        )
        journey.unified_event(
            EventType.WEBHOOK_DELAYED, EventSource.SYSTEM, 8 + 12 * 60 + 6,
            payload={"provider_event_id": provider_event_id,
                     "delay_minutes": 12 * 60},
        )

        # 3. The confirmation SLA expires while the order is still unconfirmed.
        journey.unified_event(
            EventType.ORDER_NOT_CONFIRMED, EventSource.SYSTEM, 12 * 60 + 25,
            payload={"external_order_id": journey.order.external_order_id,
                     "reason": "confirmation_sla_expired",
                     "sla_minutes": 60},
        )

        # 4. The reservation expires (order never confirmed); a late
        #    allocation attempt hits empty stock and no fulfillment exists.
        journey.release(product, quantity, 24 * 60 + 30, expired=True)
        journey.reserve(25 * 60 + 30, force_out_of_stock=True)
        journey.unified_event(
            EventType.NO_FULFILLMENT, EventSource.SYSTEM, 26 * 60 + 30,
            payload={"reason": "no_confirmation_no_fulfillment"},
        )

        # 5. The customer complains via support.
        message = CustomerMessage(
            id=_uuid5(journey.seed, f"msg:{journey.index}", 0),
            customer_id=journey.order.customer_id,
            order_id=journey.order.id,
            channel=CustomerMessageChannel.SUPPORT,
            direction=CustomerMessageDirection.INBOUND,
            message=(
                f"I paid for order {journey.order.external_order_id} more than a "
                "day ago. It was never confirmed, never shipped, and nobody has "
                "contacted me. I want my money back."
            ),
            timestamp=journey.at(27 * 60),
            metadata_={"about": "compound_failure", "intent": "complaint"},
        )
        journey.records.append(message)
        journey.unified_event(
            EventType.CUSTOMER_COMPLAINT, EventSource.CUSTOMER, 27 * 60,
            payload={"message_id": str(message.id),
                     "order_id": journey.order.external_order_id},
        )