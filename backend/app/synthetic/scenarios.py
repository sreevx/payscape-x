"""Scenario definitions.

Declarative metadata for the ten synthetic scenarios. The generator uses
this registry to produce journeys; the API exposes it; tests assert against
it. No business intelligence lives here.
"""

from dataclasses import dataclass

from app.core.enums import ScenarioType


@dataclass(frozen=True)
class ScenarioDefinition:
    """Static description of one synthetic scenario type."""

    scenario_type: ScenarioType
    slug: str
    name: str
    description: str
    # Number of journeys to generate for this scenario.
    count: int


# Distribution: 150 orders total.
SCENARIO_DEFINITIONS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        ScenarioType.NORMAL_SUCCESS,
        "normal_success",
        "Normal Success",
        "Payment captured, webhook processed, stock reserved, fulfilled, shipped and delivered.",
        70,
    ),
    ScenarioDefinition(
        ScenarioType.PAYMENT_FAILED,
        "payment_failed",
        "Payment Failed",
        "Payment attempt is declined; no capture ever occurs.",
        15,
    ),
    ScenarioDefinition(
        ScenarioType.DUPLICATE_WEBHOOK,
        "duplicate_webhook",
        "Duplicate Webhook",
        "The same provider webhook (same provider event id) is delivered twice.",
        10,
    ),
    ScenarioDefinition(
        ScenarioType.DELAYED_WEBHOOK,
        "delayed_webhook",
        "Delayed Webhook",
        "Capture succeeds but the provider webhook arrives hours later than expected.",
        10,
    ),
    ScenarioDefinition(
        ScenarioType.INVENTORY_FAILURE,
        "inventory_failure",
        "Inventory Failure",
        "Payment captured but stock is unavailable at allocation; no fulfillment is created.",
        10,
    ),
    ScenarioDefinition(
        ScenarioType.DELIVERY_FAILURE,
        "delivery_failure",
        "Delivery Failure",
        "Payment captured, fulfilled and shipped, but delivery fails.",
        10,
    ),
    ScenarioDefinition(
        ScenarioType.REFUND_FLOW,
        "refund_flow",
        "Refund Flow",
        "Order cancelled after capture; refund initiated and completed.",
        10,
    ),
    ScenarioDefinition(
        ScenarioType.MISSING_EVENT,
        "missing_event",
        "Missing Event",
        "Capture succeeds but the expected provider webhook event is absent.",
        5,
    ),
    ScenarioDefinition(
        ScenarioType.CONTRADICTORY_EVENT,
        "contradictory_event",
        "Contradictory Event",
        "Events contradict each other (captured followed by failed) — stored, not judged.",
        5,
    ),
    ScenarioDefinition(
        ScenarioType.COMPOUND_FAILURE,
        "compound_failure",
        "Compound Failure",
        "Delayed webhook, unconfirmed order, expired reservation, out-of-stock, no fulfillment and a customer complaint compound into one journey.",
        5,
    ),
]

SCENARIO_BY_SLUG: dict[str, ScenarioDefinition] = {
    definition.slug: definition for definition in SCENARIO_DEFINITIONS
}

SCENARIO_BY_TYPE: dict[ScenarioType, ScenarioDefinition] = {
    definition.scenario_type: definition for definition in SCENARIO_DEFINITIONS
}

TOTAL_JOURNEYS = sum(definition.count for definition in SCENARIO_DEFINITIONS)


def definition_for(value: str) -> ScenarioDefinition:
    """Resolve either a slug (normal_success) or type value (NORMAL_SUCCESS)."""
    normalized = value.strip().upper().replace("-", "_")
    by_type = {t.value: d for t, d in SCENARIO_BY_TYPE.items()}
    return SCENARIO_BY_SLUG.get(value.strip(), by_type.get(normalized))  # type: ignore[return-value]