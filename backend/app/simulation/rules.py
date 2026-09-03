"""Simulation rule registry (Part 7).

A dedicated deterministic registry of the six lab interventions. Each rule
carries:

- rule_id / name / description / priority / prerequisites
- deterministic evaluation logic returning a SimulationVerdict

A verdict decides WHETHER the intervention can act in this journey and WHAT
it would change in the simulated world:

- SIMULATED         — the intervention is simulated (possibly with a doctored
                      event view, e.g. alternative stock or a refund)
- NOT_APPLICABLE    — the intervention is irrelevant to this journey
- NOT_EFFECTIVE     — applicable in principle, but its deterministic
                      prerequisites are unsatisfied (e.g. no alternative
                      stock is recorded)
- NOT_SUPPORTED     — the dataset cannot support the action (e.g. no
                      substitute-product relationship exists)

The engine NEVER silently simulates an impossible action and NEVER invents
inventory, substitutes or downstream deliveries: a simulated remedy only
removes the failure records it deterministically resolves, and everything
that would still be unrecorded keeps the outcome honest (UNVERIFIABLE rather
than an invented FULFILLED). Refund containment adds hypothetical refund
records that are clearly marked SIMULATED and only change the consequence
chain — never the delivery state.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.events import EventType
from app.simulation.models import (
    INTERVENTION_ALTERNATIVE_INVENTORY,
    INTERVENTION_DO_NOTHING,
    INTERVENTION_HUMAN_REVIEW,
    INTERVENTION_REFUND,
    INTERVENTION_RETRY_FULFILLMENT,
    INTERVENTION_SUBSTITUTE_PRODUCT,
    SIM_STATUS_NOT_APPLICABLE,
    SIM_STATUS_NOT_EFFECTIVE,
    SIM_STATUS_NOT_SUPPORTED,
    SIM_STATUS_SIMULATED,
    FailureRef,
    InterventionDef,
)

# Event types a verdict may remove from the simulated world.
_ET = EventType

FULFILLMENT_FAILURE_TYPES = frozenset({
    _ET.NO_FULFILLMENT.value,
    _ET.FULFILLMENT_FAILED.value,
})

# Inventory-stage chain node kinds (also implies OUT_OF_STOCK was recorded).
INVENTORY_FAILURE_KINDS = frozenset({
    "INVENTORY_ALLOCATION_FAILED",
    "INVENTORY_RESERVATION_EXPIRED",
})

FULFILLMENT_FAILURE_KINDS = frozenset({
    "FULFILLMENT_NOT_CREATED",
    "FULFILLMENT_FAILED",
})

REFUND_RECORDED_TYPES = frozenset({
    _ET.REFUND_INITIATED.value,
    _ET.REFUND_COMPLETED.value,
    _ET.PAYMENT_REFUNDED.value,
})


@dataclass
class SimulationVerdict:
    """Deterministic decision of one simulation rule for one journey."""

    status: str
    reason: str
    # Event ids whose records are "remediated" in the simulated world.
    remove_event_ids: tuple[str, ...] = ()
    # When true the engine replays the world with hypothetical refund
    # records appended (clearly marked SIMULATED).
    simulate_refund: bool = False
    assumptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationRule:
    """One entry of the simulation rule registry."""

    rule_id: str
    name: str
    description: str
    priority: int
    intervention: InterventionDef
    evaluate: Callable[["SimulationInputs"], SimulationVerdict]


@dataclass
class SimulationInputs:
    """Everything a rule may read — all precomputed, all deterministic.

    The engine builds this once per request from the real Part 3-6 analysis
    objects plus deterministic data facts (per-SKU stock availability).
    """

    transaction_id: str
    journey: object
    outcome: object
    failure: object
    impact: object
    present_types: frozenset[str]
    chain_refs: list[FailureRef]
    chain_kinds: frozenset[str]
    # shortage_skus / requested_by_sku / inventory_available: deterministic
    # stock facts loaded by the service (final InventoryRecord snapshot).
    shortage_skus: list[str] = field(default_factory=list)
    requested_by_sku: dict = field(default_factory=dict)
    inventory_available: dict = field(default_factory=dict)
    # substitute_skus: explicit substitute-product relationships, if the
    # dataset ever records them (empty in the synthetic catalogue).
    substitute_by_sku: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rule 1 — DO NOTHING (baseline reference)
# ---------------------------------------------------------------------------

def _do_nothing(inp: SimulationInputs) -> SimulationVerdict:
    return SimulationVerdict(
        SIM_STATUS_SIMULATED,
        "No intervention is applied — this is the baseline reference: the "
        "observed failure chain is left unchanged.",
        assumptions=[
            "The simulated world is identical to the observed records.",
            "No action is taken; the failure chain remains exactly as recorded.",
        ],
    )


_RULE_DO_NOTHING = SimulationRule(
    "SIM_DO_NOTHING",
    "Do nothing",
    "Baseline reference. The simulated world equals the observed records; "
    "used as the comparison anchor for every other intervention.",
    10,
    InterventionDef(
        INTERVENTION_DO_NOTHING,
        "Do Nothing",
        "Take no action — the observed outcome and impact remain unchanged.",
    ),
    _do_nothing,
)


# ---------------------------------------------------------------------------
# Rule 2 — ALTERNATIVE INVENTORY
# ---------------------------------------------------------------------------

def _alternative_inventory(inp: SimulationInputs) -> SimulationVerdict:
    if not inp.shortage_skus:
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "No inventory-allocation failure is recorded for this "
            "transaction, so alternative inventory is not applicable.",
        )
    missing = [
        sku
        for sku in inp.shortage_skus
        if inp.inventory_available.get(sku, 0) < inp.requested_by_sku.get(sku, 1)
    ]
    if missing:
        detail = ", ".join(
            f"{sku} (available {inp.inventory_available.get(sku, 0)}, "
            f"requested {inp.requested_by_sku.get(sku, 1)})"
            for sku in sorted(missing)
        )
        return SimulationVerdict(
            SIM_STATUS_NOT_EFFECTIVE,
            "No alternative stock is recorded for the shortage SKU(s): "
            f"{detail}. The simulation does not invent inventory.",
            assumptions=[
                "Alternative stock is only assumed when an inventory record "
                "actually shows enough available quantity.",
                "No alternative stock exists in the dataset for this shortage.",
            ],
        )
    # Alternative stock exists for every shortage SKU: remove the recorded
    # shortage and the inventory-caused fulfillment markers so the engines
    # replay the world where allocation succeeded.
    remove_ids = _ids_of_type(inp, _ET.INVENTORY_OUT_OF_STOCK.value)
    if _ET.ORDER_NOT_CONFIRMED.value not in inp.present_types:
        remove_ids += _ids_of_type(inp, *FULFILLMENT_FAILURE_TYPES)
    return SimulationVerdict(
        SIM_STATUS_SIMULATED,
        "Alternative stock is recorded for the required SKU(s); allocation "
        "is simulated as successful.",
        remove_event_ids=tuple(remove_ids),
        assumptions=[
            "Simulation assumes the alternative stock is available at the "
            "moment allocation is retried.",
            "The simulated world does not assert downstream fulfillment or "
            "delivery — those stages still depend on separate operations.",
        ],
    )


_RULE_ALTERNATIVE_INVENTORY = SimulationRule(
    "SIM_ALTERNATIVE_INVENTORY",
    "Reserve alternative inventory",
    "When inventory allocation failed and an inventory record shows enough "
    "available stock for the required SKU, simulate a successful allocation. "
    "Never invents stock: without a record, the intervention is "
    "NOT_EFFECTIVE.",
    20,
    InterventionDef(
        INTERVENTION_ALTERNATIVE_INVENTORY,
        "Reserve Alternative Inventory",
        "Simulate allocating alternative stock for the product that ran out "
        "of stock.",
    ),
    _alternative_inventory,
)


# ---------------------------------------------------------------------------
# Rule 3 — RETRY FULFILLMENT
# ---------------------------------------------------------------------------

def _retry_fulfillment(inp: SimulationInputs) -> SimulationVerdict:
    fulfillment_problem = bool(
        inp.chain_kinds & FULFILLMENT_FAILURE_KINDS
        or inp.present_types & FULFILLMENT_FAILURE_TYPES
    )
    if not fulfillment_problem:
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "No fulfillment-stage failure is recorded for this transaction "
            "(no NO_FULFILLMENT / FULFILLMENT_FAILED), so there is nothing "
            "to retry.",
        )
    inventory_problem = bool(
        inp.chain_kinds & INVENTORY_FAILURE_KINDS
        or _ET.INVENTORY_OUT_OF_STOCK.value in inp.present_types
    )
    if inventory_problem:
        missing = [
            sku
            for sku in inp.shortage_skus
            if inp.inventory_available.get(sku, 0) < inp.requested_by_sku.get(sku, 1)
        ]
        if missing:
            return SimulationVerdict(
                SIM_STATUS_NOT_EFFECTIVE,
                "A fulfillment retry cannot succeed while the required stock "
                "allocation is still failed and no alternative stock is "
                "recorded — inventory must be resolved first.",
                assumptions=[
                    "The simulation never creates stock out of nothing.",
                    "Fulfillment retry is only effective after the inventory "
                    "shortage is resolved by another intervention.",
                ],
            )
    remove_ids = _ids_of_type(inp, *FULFILLMENT_FAILURE_TYPES)
    return SimulationVerdict(
        SIM_STATUS_SIMULATED,
        "Fulfillment is retried and simulated as completing; the recorded "
        "fulfillment failure markers are removed from the simulated world.",
        remove_event_ids=tuple(remove_ids),
        assumptions=[
            "Simulation assumes the fulfillment retry succeeds.",
            "The simulated world does not assert shipment or delivery — "
            "those stages still depend on separate operations.",
        ],
    )


_RULE_RETRY_FULFILLMENT = SimulationRule(
    "SIM_RETRY_FULFILLMENT",
    "Retry fulfillment",
    "Applicable when fulfillment failed or was blocked. Recovery is only "
    "simulated when its deterministic prerequisites are satisfied — a "
    "retry cannot succeed while the stock allocation is still failed.",
    30,
    InterventionDef(
        INTERVENTION_RETRY_FULFILLMENT,
        "Retry Fulfillment",
        "Simulate retrying the fulfillment operation after its failure.",
    ),
    _retry_fulfillment,
)


# ---------------------------------------------------------------------------
# Rule 4 — SUBSTITUTE PRODUCT
# ---------------------------------------------------------------------------

def _substitute_product(inp: SimulationInputs) -> SimulationVerdict:
    # The synthetic catalogue records no substitute-product relationships.
    # SUBSTITUTE_PRODUCT is only supported when an explicit relationship
    # exists in the dataset — never fabricated on the fly.
    skus = inp.shortage_skus or list(inp.requested_by_sku.keys())
    available_substitutes = {
        sku: sorted(inp.substitute_by_sku.get(sku, [])) for sku in skus
    }
    if skus and any(available_substitutes.values()):
        return SimulationVerdict(
            SIM_STATUS_SIMULATED,
            "A substitute product is recorded for the ordered SKU(s); "
            "substitution is simulated as successful.",
            remove_event_ids=tuple(_ids_of_type(inp, _ET.INVENTORY_OUT_OF_STOCK.value)),
            assumptions=[
                "Simulation assumes the customer accepts the substitute "
                "product.",
                "Simulation does not model real-world customer behaviour.",
            ],
        )
    return SimulationVerdict(
        SIM_STATUS_NOT_SUPPORTED,
        "No substitute-product relationship is recorded in the dataset for "
        "the ordered SKU(s) — the simulation does not fabricate "
        "substitutions.",
        assumptions=[
            "Substitute products require an explicit product relationship "
            "in the catalogue.",
            "The synthetic dataset contains no substitute relationships.",
        ],
    )


_RULE_SUBSTITUTE_PRODUCT = SimulationRule(
    "SIM_SUBSTITUTE_PRODUCT",
    "Offer substitute product",
    "Only simulated when the dataset contains a legitimate substitute "
    "relationship for the ordered SKU. Otherwise NOT_SUPPORTED — never "
    "fabricated.",
    40,
    InterventionDef(
        INTERVENTION_SUBSTITUTE_PRODUCT,
        "Offer Substitute Product",
        "Simulate offering a substitute product for the unavailable SKU.",
    ),
    _substitute_product,
)


# ---------------------------------------------------------------------------
# Rule 5 — REFUND (financial / customer containment)
# ---------------------------------------------------------------------------

def _refund(inp: SimulationInputs) -> SimulationVerdict:
    refund_recorded = bool(inp.present_types & REFUND_RECORDED_TYPES)
    if refund_recorded:
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "A refund is already recorded for this payment — there is "
            "nothing new to simulate.",
        )
    if _ET.PAYMENT_CAPTURED.value not in inp.present_types:
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "No payment was captured for this transaction — there is "
            "nothing to refund.",
        )
    if getattr(inp.outcome, "outcome", None) != "FAILED":
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "Refund containment is only simulated for definitive business "
            "failures (outcome FAILED). A refund would not change an "
            "unverifiable or fulfilled outcome.",
        )
    return SimulationVerdict(
        SIM_STATUS_SIMULATED,
        "A completed refund is simulated. Refund containment changes the "
        "consequence chain (refund records replace the potential dispute "
        "risk) but never the delivery state.",
        simulate_refund=True,
        assumptions=[
            "Simulation assumes refund initiation and completion succeed "
            "within a standard processing window.",
            "A refund returns the captured amount; it does not deliver the "
            "goods — the simulated business outcome stays FAILED.",
            "Simulation does not model real-world customer behaviour or "
            "dispute outcomes.",
        ],
    )


_RULE_REFUND = SimulationRule(
    "SIM_REFUND_CONTAINMENT",
    "Refund the customer",
    "Simulate financial/customer containment for a definitive business "
    "failure on a captured payment. A refund changes the consequence chain "
    "— it never fixes fulfillment and never claims delivery.",
    50,
    InterventionDef(
        INTERVENTION_REFUND,
        "Refund Customer",
        "Simulate issuing a full refund for the captured payment.",
    ),
    _refund,
)


# ---------------------------------------------------------------------------
# Rule 6 — HUMAN REVIEW
# ---------------------------------------------------------------------------

def _human_review(inp: SimulationInputs) -> SimulationVerdict:
    if getattr(inp.outcome, "outcome", None) == "FULFILLED":
        return SimulationVerdict(
            SIM_STATUS_NOT_APPLICABLE,
            "The transaction is already fulfilled — there is nothing to "
            "escalate to human operations.",
        )
    return SimulationVerdict(
        SIM_STATUS_SIMULATED,
        "The case is escalated to human operations for review. Human review "
        "is simulated as a possible action without asserting any recovery.",
        assumptions=[
            "Human review does not guarantee recovery — no deterministic "
            "outcome change is asserted.",
            "The simulation does not model the outcome of a manual "
            "investigation.",
        ],
    )


_RULE_HUMAN_REVIEW = SimulationRule(
    "SIM_HUMAN_REVIEW",
    "Escalate to human review",
    "Simulate escalation to human operations. Never claims that review "
    "guarantees recovery — the simulated world stays identical to the "
    "observed records.",
    60,
    InterventionDef(
        INTERVENTION_HUMAN_REVIEW,
        "Human Review",
        "Escalate the failed transaction to human operations for review.",
    ),
    _human_review,
)


# ---------------------------------------------------------------------------
# The registry — evaluation order is fixed (priority, then registry order).
# ---------------------------------------------------------------------------

SIMULATION_RULES: list[SimulationRule] = [
    _RULE_DO_NOTHING,
    _RULE_ALTERNATIVE_INVENTORY,
    _RULE_RETRY_FULFILLMENT,
    _RULE_SUBSTITUTE_PRODUCT,
    _RULE_REFUND,
    _RULE_HUMAN_REVIEW,
]

RULE_BY_INTERVENTION: dict[str, SimulationRule] = {
    rule.intervention.intervention_type: rule for rule in SIMULATION_RULES
}


def _ids_of_type(inp: SimulationInputs, *event_types: str) -> list[str]:
    """Deterministic event ids of the given types in this journey."""
    events = getattr(inp.journey, "chronological_events", [])
    return sorted(
        event.event_id
        for event in events
        if event.event_type in event_types
    )
