"""Simulation Lab (Part 7).

Deterministic, read-only counterfactual lab: for an already-analyzed
transaction it replays possible interventions (do nothing, retry
fulfillment, alternative inventory, substitute product, refund, human
review) against the real journey / evidence / consistency / outcome /
compound-failure / impact records.

Every result is labelled SIMULATED — a scenario estimate, never an actual
outcome, a prediction or a guarantee. Same database state + same
intervention => identical result. No LLM, no ML, no randomness, no external
calls, and no writes: the lab never modifies payments, orders, inventory,
refunds or webhooks.
"""

from app.simulation.engine import simulate
from app.simulation.models import (
    ALL_INTERVENTIONS,
    ALL_SIM_STATUSES,
    CompareItem,
    FailureRef,
    InterventionDef,
    RiskRef,
    SimulationBaseline,
    SimulationReport,
    SimulationResult,
)
from app.simulation.rules import RULE_BY_INTERVENTION, SIMULATION_RULES

__all__ = [
    "ALL_INTERVENTIONS",
    "ALL_SIM_STATUSES",
    "CompareItem",
    "FailureRef",
    "InterventionDef",
    "RULE_BY_INTERVENTION",
    "RiskRef",
    "SIMULATION_RULES",
    "SimulationBaseline",
    "SimulationReport",
    "SimulationResult",
    "simulate",
]
