"""Tests for the deterministic synthetic dataset generator.

Covers determinism, dataset shape, scenario distribution, correlation
integrity and the specific journey shapes of each scenario — including the
intentionally "broken" ones (missing event, contradictory event, compound
failure), which must be generated as designed and never repaired.
"""

import uuid
from collections import Counter

import pytest

from app.core.enums import ScenarioType, WebhookProcessingStatus
from app.models import (
    CustomerMessage,
    Fulfillment,
    Refund,
    ScenarioInstance,
    Shipment,
    TransactionEvent,
    Webhook,
)
from app.synthetic.generator import Dataset, DatasetGenerator
from app.synthetic.scenarios import SCENARIO_DEFINITIONS


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    """One deterministic dataset shared by the whole module (seed 42)."""
    return DatasetGenerator(seed=42).generate()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def journey_events(dataset: Dataset, scenario_type: ScenarioType):
    """(instance, ordered events) pairs for one scenario type."""
    pairs = [
        (instance, events)
        for instance, events in dataset.journeys
        if instance.scenario_type is scenario_type
    ]
    for instance, events in pairs:
        events.sort(key=lambda e: (e.timestamp, str(e.id)))
    return pairs


def types_of(events) -> list[str]:
    return [event.event_type.value for event in events]


def first_journey(dataset: Dataset, scenario_type: ScenarioType):
    pairs = journey_events(dataset, scenario_type)
    assert pairs, f"no journeys of type {scenario_type}"
    return pairs[0]


def records_of(dataset: Dataset, instance: ScenarioInstance, model):
    """Domain records of `model` for a journey, matched via its order or payment."""
    order_id = uuid.UUID(instance.metadata_["order_id"])
    payment_id = uuid.UUID(instance.metadata_["payment_id"])
    return [
        record for record in dataset.records
        if isinstance(record, model)
        and (
            getattr(record, "payment_id", None) == payment_id
            or getattr(record, "order_id", None) == order_id
        )
    ]


def assert_subsequence(haystack: list[str], needle: list[str]) -> None:
    """Every item of `needle` appears in `haystack` in order."""
    iterator = iter(haystack)
    for expected in needle:
        for actual in iterator:
            if actual == expected:
                break
        else:
            raise AssertionError(f"{expected} not found after previous items in {haystack}")


# ---------------------------------------------------------------------------
# determinism + shape
# ---------------------------------------------------------------------------

def test_generator_is_deterministic():
    first = DatasetGenerator(seed=42).generate()
    second = DatasetGenerator(seed=42).generate()

    def fingerprint(d: Dataset) -> tuple:
        return (
            d.summarize(),
            [e.id for e in d.unified],
            [(e.event_type.value, e.timestamp, e.correlation_id)
             for e in d.unified],
            [record.id for record in d.records],
        )

    assert fingerprint(first) == fingerprint(second)

    # A different seed must produce a different dataset.
    other = DatasetGenerator(seed=7).generate()
    assert [e.id for e in other.unified] != [e.id for e in first.unified]


def test_dataset_shape_and_merchant(dataset: Dataset):
    summary = dataset.summarize()
    assert summary["merchant"] == "NovaCart Commerce"
    assert summary["customers"] == 100
    assert summary["products"] == 30
    assert summary["orders"] == 150
    assert summary["payments"] == 150
    assert summary["transaction_events"] >= 1500

    # Merchant fields are complete.
    merchant = dataset.merchant
    assert merchant.external_id == "novacart_commerce"
    assert merchant.currency == "INR"
    assert merchant.timezone

    # All customers are synthetic and non-empty.
    customers = dataset.customers
    assert len({customer.email for customer in customers}) == 100
    for customer in customers:
        assert customer.email.endswith("@example.in")
        assert customer.name.strip()


def test_scenario_distribution_matches_definitions(dataset: Dataset):
    counts = Counter(instance.scenario_type for instance in dataset.instances)
    for definition in SCENARIO_DEFINITIONS:
        assert (
            counts[definition.scenario_type] == definition.count
        ), definition.scenario_type
    assert sum(counts.values()) == 150


def test_every_event_matches_a_scenario_correlation(dataset: Dataset):
    correlations = {instance.correlation_id for instance in dataset.instances}
    assert len(correlations) == 150
    for event in dataset.unified:
        assert event.correlation_id in correlations
        assert event.order_id is not None
    # Every scenario instance owns its own journey id.
    journey_indexes = [
        instance.metadata_["journey_index"] for instance in dataset.instances
    ]
    assert len(journey_indexes) == len(set(journey_indexes))


def test_every_journey_timeline_is_chronological(dataset: Dataset):
    """The unified stream per journey is strictly chronological."""
    for instance, events in dataset.journeys:
        stamps = [event.timestamp for event in events]
        assert stamps == sorted(stamps), instance.scenario_type


def test_entity_count_consistency(dataset: Dataset):
    """Journeys that need domain entities actually have them."""
    has_webhook = set()
    has_shipment = set()
    has_refund = set()
    has_message = set()
    for record in dataset.records:
        if isinstance(record, Webhook):
            has_webhook.add(record.payment_id)
        if isinstance(record, Shipment):
            has_shipment.add(record.order_id)
        if isinstance(record, Refund):
            has_refund.add(record.payment_id)
        if isinstance(record, CustomerMessage):
            has_message.add(record.order_id)

    orders = {record.id for record in dataset.orders}
    payments = {record.id for record in dataset.payments}
    assert has_webhook <= payments
    assert has_shipment <= orders
    assert has_refund <= payments
    assert has_message <= orders


# ---------------------------------------------------------------------------
# SCENARIO 1 — NORMAL SUCCESS
# ---------------------------------------------------------------------------

def test_normal_success_complete_journey(dataset: Dataset):
    instance, events = first_journey(dataset, ScenarioType.NORMAL_SUCCESS)
    types = types_of(events)
    assert_subsequence(types, [
        "ORDER_CREATED",
        "PAYMENT_CREATED",
        "PAYMENT_AUTHORIZED",
        "PAYMENT_CAPTURED",
        "WEBHOOK_SENT",
        "WEBHOOK_RECEIVED",
        "ORDER_CONFIRMED",
        "INVENTORY_RESERVED",
        "FULFILLMENT_CREATED",
        "FULFILLMENT_PROCESSING",
        "FULFILLMENT_PACKED",
        "FULFILLMENT_SHIPPED",
        "SHIPMENT_CREATED",
        "SHIPMENT_IN_TRANSIT",
        "DELIVERY_OUT_FOR_DELIVERY",
        "DELIVERY_COMPLETED",
    ])
    # Every normal journey ends with a delivered order.
    for instance, events in journey_events(dataset, ScenarioType.NORMAL_SUCCESS):
        assert types_of(events)[-1] == "DELIVERY_COMPLETED"


def test_normal_success_domain_records(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.NORMAL_SUCCESS):
        shipment = records_of(dataset, instance, Shipment)
        assert len(shipment) == 1
        assert shipment[0].actual_delivery_at is not None
        assert shipment[0].status.value == "DELIVERED"


# ---------------------------------------------------------------------------
# SCENARIO 2 — PAYMENT FAILED
# ---------------------------------------------------------------------------

def test_payment_failed_never_captures(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.PAYMENT_FAILED):
        types = types_of(events)
        assert "PAYMENT_CAPTURED" not in types
        assert_subsequence(types, [
            "PAYMENT_CREATED", "PAYMENT_FAILED", "WEBHOOK_RECEIVED",
            "ORDER_CANCELLED",
        ])
        webhooks = records_of(dataset, instance, Webhook)
        assert len(webhooks) == 1
        assert webhooks[0].event_type == "payment.failed"


# ---------------------------------------------------------------------------
# SCENARIO 3 — DUPLICATE WEBHOOK
# ---------------------------------------------------------------------------

def test_duplicate_webhook_two_deliveries_same_identity(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.DUPLICATE_WEBHOOK):
        types = types_of(events)
        assert_subsequence(types, ["PAYMENT_CAPTURED", "WEBHOOK_RECEIVED",
                                   "WEBHOOK_DUPLICATE", "ORDER_CONFIRMED"])
        assert types.count("WEBHOOK_RECEIVED") == 1
        assert types.count("WEBHOOK_DUPLICATE") == 1

        webhooks = records_of(dataset, instance, Webhook)
        assert len(webhooks) == 2
        # Same provider event identity delivered twice.
        assert webhooks[0].provider_event_id == webhooks[1].provider_event_id
        statuses = {hook.processing_status for hook in webhooks}
        assert statuses == {
            WebhookProcessingStatus.PROCESSED,
            WebhookProcessingStatus.DUPLICATE,
        }


# ---------------------------------------------------------------------------
# SCENARIO 4 — DELAYED WEBHOOK
# ---------------------------------------------------------------------------

def test_delayed_webhook_gap_is_material(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.DELAYED_WEBHOOK):
        types = types_of(events)
        assert_subsequence(types, ["PAYMENT_CAPTURED", "WEBHOOK_SENT",
                                   "WEBHOOK_RECEIVED", "WEBHOOK_DELAYED",
                                   "ORDER_CONFIRMED"])
        captured = next(e for e in events
                        if e.event_type.value == "PAYMENT_CAPTURED")
        received = next(e for e in events
                        if e.event_type.value == "WEBHOOK_RECEIVED")
        gap_minutes = (received.timestamp - captured.timestamp).total_seconds() / 60
        assert gap_minutes > 8 * 60, f"webhook gap only {gap_minutes} minutes"
        webhooks = records_of(dataset, instance, Webhook)
        assert any(h.processing_status == WebhookProcessingStatus.DELAYED
                   for h in webhooks)


# ---------------------------------------------------------------------------
# SCENARIO 5 — PAYMENT SUCCESS + INVENTORY FAILURE
# ---------------------------------------------------------------------------

def test_inventory_failure_has_no_fulfillment(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.INVENTORY_FAILURE):
        types = types_of(events)
        assert_subsequence(types, ["PAYMENT_CAPTURED", "ORDER_CONFIRMED",
                                   "INVENTORY_OUT_OF_STOCK", "NO_FULFILLMENT"])
        assert "FULFILLMENT_CREATED" not in types
        fulfillments = [
            record for record in dataset.records
            if isinstance(record, Fulfillment)
            and str(record.order_id) == instance.metadata_["order_id"]
        ]
        assert fulfillments == []


# ---------------------------------------------------------------------------
# SCENARIO 6 — PAYMENT SUCCESS + DELIVERY FAILURE
# ---------------------------------------------------------------------------

def test_delivery_failure_ends_returned(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.DELIVERY_FAILURE):
        types = types_of(events)
        assert_subsequence(types, ["PAYMENT_CAPTURED", "SHIPMENT_CREATED",
                                   "DELIVERY_FAILED", "DELIVERY_RETURNED"])
        message_records = [
            record for record in dataset.records
            if isinstance(record, CustomerMessage)
            and str(record.order_id) == instance.metadata_["order_id"]
        ]
        assert message_records, "expected a customer complaint message"


# ---------------------------------------------------------------------------
# SCENARIO 7 — REFUND FLOW
# ---------------------------------------------------------------------------

def test_refund_flow_full_cycle(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.REFUND_FLOW):
        types = types_of(events)
        assert_subsequence(types, ["PAYMENT_CAPTURED", "ORDER_CANCELLED",
                                   "REFUND_INITIATED", "REFUND_COMPLETED",
                                   "PAYMENT_REFUNDED"])
        refunds = records_of(dataset, instance, Refund)
        assert len(refunds) == 1
        assert refunds[0].status.value == "COMPLETED"
        assert refunds[0].completed_at is not None
        assert refunds[0].provider_refund_id.startswith("rfnd_")
        assert refunds[0].payment_id is not None


# ---------------------------------------------------------------------------
# SCENARIO 8 — MISSING EVENT
# ---------------------------------------------------------------------------

def test_missing_event_omits_webhook_received(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.MISSING_EVENT):
        types = types_of(events)
        assert "PAYMENT_CAPTURED" in types
        # The expected provider webhook is deliberately absent.
        assert "WEBHOOK_RECEIVED" not in types
        # No later lifecycle events either (journey stalls after capture).
        assert "ORDER_CONFIRMED" not in types


# ---------------------------------------------------------------------------
# SCENARIO 9 — CONTRADICTORY EVENT
# ---------------------------------------------------------------------------

def test_contradictory_event_captured_then_failed(dataset: Dataset):
    for instance, events in journey_events(dataset, ScenarioType.CONTRADICTORY_EVENT):
        types = types_of(events)
        assert "PAYMENT_CAPTURED" in types
        assert "PAYMENT_FAILED" in types
        captured_index = types.index("PAYMENT_CAPTURED")
        failed_index = types.index("PAYMENT_FAILED")
        # The contradiction is stored as generated — captured before failed.
        assert captured_index < failed_index
        webhooks = records_of(dataset, instance, Webhook)
        hook_types = {hook.event_type for hook in webhooks}
        assert {"payment.captured", "payment.failed"} <= hook_types


# ---------------------------------------------------------------------------
# SCENARIO 10 — COMPOUND FAILURE
# ---------------------------------------------------------------------------

def test_compound_failure_full_chain(dataset: Dataset):
    instance, events = first_journey(dataset, ScenarioType.COMPOUND_FAILURE)
    types = types_of(events)
    # Stock is reserved right after capture, then expires because the order
    # never gets confirmed after the delayed webhook.
    assert_subsequence(types, [
        "PAYMENT_CAPTURED",
        "INVENTORY_RESERVED",
        "WEBHOOK_RECEIVED",
        "WEBHOOK_DELAYED",
        "ORDER_NOT_CONFIRMED",
        "INVENTORY_RESERVATION_EXPIRED",
        "NO_FULFILLMENT",
        "CUSTOMER_COMPLAINT",
    ])
    # The out-of-stock signal arrives after the reservation expired.
    assert "INVENTORY_OUT_OF_STOCK" in types
    assert "FULFILLMENT_CREATED" not in types

    # Realistic time spread: complaint lands well after the capture.
    stamps = {event.event_type.value: event.timestamp for event in events}
    spread_hours = (
        stamps["CUSTOMER_COMPLAINT"] - stamps["PAYMENT_CAPTURED"]
    ).total_seconds() / 3600
    assert spread_hours > 24, f"compound failure compressed to {spread_hours}h"

    # Every compound journey ends with the customer complaint.
    for instance, events in journey_events(dataset, ScenarioType.COMPOUND_FAILURE):
        assert types_of(events)[-1] == "CUSTOMER_COMPLAINT"
