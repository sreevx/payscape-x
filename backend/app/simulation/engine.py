"""Simulation decision engine (Part 7).

Deterministically answers "what could have been done differently?" for ONE
already-analyzed transaction.

Design (documented in docs/architecture.md):

    baseline (journey + evidence + consistency + outcome + failure + impact)
        -> run SIMULATION_RULES in registry order
        -> each SIMULATED verdict that changes records replays the REAL
           Part 3-6 pipeline over an in-memory doctored journey view
        -> resolved / remaining failure references are diffed between the
           baseline chain and the simulated chain
        -> simulated impact score comes from the real impact engine replay
        -> comparison rows are ranked deterministically

The replay never touches the database: remediated records are dropped (or
hypothetical refund records appended with deterministic SIMULATED ids) on a
private copy of the journey, then the real evidence / consistency / outcome
/ failure / impact engines recompute over that view. No LLM, no randomness,
no ML, no external calls. Identical input always yields identical results.
"""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.consistency.evaluator import evaluate as evaluate_consistency
from app.core.events import EventType
from app.evidence.collector import collect as collect_evidence
from app.failures.engine import analyze as analyze_failure
from app.failures.models import CompoundFailureResult
from app.impact.engine import analyze as analyze_impact
from app.impact.models import ImpactResult
from app.journey import integrity as integrity_module
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney
from app.outcome.engine import decide as decide_outcome
from app.outcome.models import OutcomeResult
from app.simulation.models import (
    SIM_STATUS_SIMULATED,
    CompareItem,
    FailureRef,
    RiskRef,
    SimulationBaseline,
    SimulationReport,
    SimulationResult,
)
from app.simulation.rules import (
    RULE_BY_INTERVENTION,
    SIMULATION_RULES,
    SimulationInputs,
    SimulationRule,
    SimulationVerdict,
)

NAMESPACE = uuid.NAMESPACE_URL
SIMULATED_EVENT_NAMESPACE = uuid.UUID("8f5f4f4a-7b1a-4a1f-9c0a-2b2b2b2b2b2b")


def _simulation_id(transaction_id: str, intervention_type: str) -> str:
    return str(
        uuid.uuid5(
            NAMESPACE, f"payscape:simulation:{transaction_id}:{intervention_type}"
        )
    )


def _simulated_event_id(transaction_id: str, event_type: str) -> str:
    return str(
        uuid.uuid5(
            SIMULATED_EVENT_NAMESPACE,
            f"payscape:sim-event:{transaction_id}:{event_type}",
        )
    )


# ---------------------------------------------------------------------------
# Baseline helpers
# ---------------------------------------------------------------------------

def _chain_refs(failure: CompoundFailureResult) -> list[FailureRef]:
    return [
        FailureRef(kind=node.kind, label=node.label, rule_id=node.rule_id)
        for node in failure.failure_chain
    ]


def _build_inputs(journey, outcome, failure, impact, inventory_facts) -> SimulationInputs:
    present = frozenset(event.event_type for event in journey.chronological_events)
    chain_refs = _chain_refs(failure)
    return SimulationInputs(
        transaction_id=journey.transaction_id,
        journey=journey,
        outcome=outcome,
        failure=failure,
        impact=impact,
        present_types=present,
        chain_refs=chain_refs,
        chain_kinds=frozenset(ref.kind for ref in chain_refs),
        shortage_skus=list(inventory_facts.shortage_skus or []),
        requested_by_sku=dict(inventory_facts.requested_by_sku or {}),
        inventory_available=dict(inventory_facts.inventory_available or {}),
        substitute_by_sku=dict(inventory_facts.substitute_by_sku or {}),
    )


def _baseline_view(journey, outcome, failure, impact) -> SimulationBaseline:
    return SimulationBaseline(
        transaction_id=journey.transaction_id,
        outcome=outcome.outcome,
        confidence=outcome.confidence,
        consistency_status=outcome.consistency_status,
        compound_failure_detected=failure.detected,
        severity=failure.severity if failure.detected else (
            impact.severity if impact is not None else "LOW"
        ),
        impact_score=impact.impact_score if impact is not None else 0.0,
        impact_scope=impact.scope if impact is not None else "SINGLE_TRANSACTION",
        affected_transactions=(
            impact.affected_transactions if impact is not None else 1
        ),
        root_causes=[
            FailureRef(kind=root.kind, label=root.label, rule_id=root.rule_id)
            for root in failure.root_causes
        ],
        event_ids=sorted(
            set(outcome.supporting_event_ids) | set(failure.event_ids)
        ),
        evidence_ids=sorted(
            set(outcome.supporting_evidence_ids) | set(failure.evidence_ids)
        ),
    )


# ---------------------------------------------------------------------------
# Doctored journey construction + replay
# ---------------------------------------------------------------------------

def _copy_event(event: JourneyEvent) -> JourneyEvent:
    return replace(
        event,
        is_duplicate=False,
        is_unknown=False,
        is_orphan=False,
        duplicate_of_event_id=None,
    )


def _refund_events(journey: ReconstructedJourney) -> list[JourneyEvent]:
    """Hypothetical refund records appended AFTER the observed timeline.

    Every event carries a deterministic SIMULATED id and a payload flag so
    it can never be confused with a real record.
    """
    events = journey.chronological_events
    # Fixed epoch fallback keeps the replay deterministic even for a
    # hypothetical empty journey (impossible in practice — every seeded
    # payment has ORDER_CREATED..PAYMENT_CREATED events).
    base_ts = (
        events[-1].timestamp
        if events
        else datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    start_position = max((event.ingestion_position for event in events), default=-1) + 1
    correlation = journey.correlation_id or journey.payment_id
    amount = ""
    for event in reversed(events):
        if event.event_type == EventType.PAYMENT_CAPTURED.value:
            amount = str(event.payload.get("amount", ""))
            break

    def build(event_type: EventType, minutes: float) -> JourneyEvent:
        return JourneyEvent(
            event_id=_simulated_event_id(journey.transaction_id, event_type.value),
            order_id=journey.order_id,
            payment_id=journey.payment_id,
            event_type=event_type.value,
            source="PAYMENT_PROVIDER",
            timestamp=base_ts + timedelta(minutes=minutes),
            correlation_id=correlation,
            idempotency_key=None,
            payload={
                "simulated": True,
                "simulation": "REFUND",
                "amount": amount,
            },
            ingestion_position=start_position,
        )

    return [
        build(EventType.REFUND_INITIATED, 5),
        build(EventType.REFUND_COMPLETED, 35),
    ]


def _doctored_journey(
    journey: ReconstructedJourney,
    remove_event_ids: tuple[str, ...],
    simulate_refund: bool,
) -> ReconstructedJourney:
    """Private in-memory view of the journey under the intervention."""
    removed = set(remove_event_ids)
    kept = [
        _copy_event(event)
        for event in journey.chronological_events
        if event.event_id not in removed
    ]
    events = kept
    if simulate_refund:
        events = kept + _refund_events(journey)
    chronological = sorted(events, key=lambda event: (event.timestamp, event.event_id))
    ingestion = sorted(events, key=lambda event: event.ingestion_position)
    return ReconstructedJourney(
        transaction_id=journey.transaction_id,
        order_id=journey.order_id,
        payment_id=journey.payment_id,
        correlation_id=journey.correlation_id,
        chronological_events=chronological,
        ingestion_events=ingestion,
    )


def _replay(journey_d: ReconstructedJourney, webhooks, context, cross):
    """Re-run the real Part 3-6 engines over the doctored journey view."""
    integrity_d = integrity_module.analyze(journey_d, webhooks)
    evidence_d = collect_evidence(journey_d, integrity_d, context)
    consistency_d = evaluate_consistency(journey_d, context)
    outcome_d = decide_outcome(journey_d, integrity_d, evidence_d, consistency_d)
    failure_d = analyze_failure(
        journey_d, integrity_d, evidence_d, consistency_d, outcome_d
    )
    impact_d = analyze_impact(
        journey_d, integrity_d, evidence_d, consistency_d, outcome_d, failure_d, cross
    )
    return outcome_d, failure_d, impact_d


def _diff_chain(baseline_refs: list[FailureRef], simulated: CompoundFailureResult):
    """(resolved, remaining) failure references between the two chains."""
    simulated_refs = _chain_refs(simulated)
    simulated_kinds = {ref.kind for ref in simulated_refs}
    resolved = [ref for ref in baseline_refs if ref.kind not in simulated_kinds]
    return resolved, simulated_refs


def _rule_ids_for(result_rule: SimulationRule, outcome_d: OutcomeResult,
                  simulated: CompoundFailureResult) -> list[str]:
    ids = [result_rule.rule_id]
    if outcome_d is not None:
        ids.append(outcome_d.primary_reason.rule_id)
    ids.extend(ref.rule_id for ref in _chain_refs(simulated))
    return sorted(set(ids))


# ---------------------------------------------------------------------------
# Simulation assembly
# ---------------------------------------------------------------------------

def _result_for(
    inputs: SimulationInputs,
    rule: SimulationRule,
    verdict: SimulationVerdict,
    outcome: OutcomeResult,
    failure: CompoundFailureResult,
    impact: Optional[ImpactResult],
    baseline_view: SimulationBaseline,
    webhooks,
    context,
    cross,
) -> SimulationResult:
    transaction_id = inputs.transaction_id
    sim_outcome = outcome
    sim_failure = failure
    sim_impact = impact
    removed_ids: list[str] = []
    sim_event_ids: list[str] = []

    if verdict.status == SIM_STATUS_SIMULATED and (
        verdict.remove_event_ids or verdict.simulate_refund
    ):
        removed_ids = list(verdict.remove_event_ids)
        journey_d = _doctored_journey(
            inputs.journey, verdict.remove_event_ids, verdict.simulate_refund
        )
        if verdict.simulate_refund:
            sim_event_ids = [
                event.event_id for event in _refund_events(inputs.journey)
            ]
        outcome_d, failure_d, impact_d = _replay(
            journey_d, webhooks, context, cross
        )
        sim_outcome, sim_failure, sim_impact = outcome_d, failure_d, impact_d

    resolved, remaining = _diff_chain(_chain_refs(failure), sim_failure)

    # New risks: POTENTIAL consequences the simulated world introduced that
    # were not present in the baseline consequence set.
    baseline_potential = {
        item.rule_id
        for item in (impact.potential_consequences if impact else [])
    }
    new_risks: list[RiskRef] = []
    if sim_impact is not None:
        for item in sim_impact.potential_consequences:
            if item.rule_id not in baseline_potential:
                new_risks.append(
                    RiskRef(claim=item.claim, rule_id=item.rule_id,
                            classification=item.classification)
                )

    simulated_score = (
        round(sim_impact.impact_score, 2) if sim_impact is not None
        else baseline_view.impact_score
    )
    delta = round(simulated_score - baseline_view.impact_score, 2)

    metadata: dict = {
        "labels": {"baseline": "ACTUAL", "simulated": "SIMULATED"},
        "simulated": True,
    }
    if removed_ids:
        metadata["removed_event_ids"] = removed_ids
    if sim_event_ids:
        metadata["simulated_event_ids"] = sim_event_ids

    return SimulationResult(
        simulation_id=_simulation_id(transaction_id,
                                     rule.intervention.intervention_type),
        transaction_id=transaction_id,
        status=verdict.status,
        reason=verdict.reason,
        intervention=rule.intervention,
        baseline_outcome=baseline_view.outcome,
        baseline_confidence=round(baseline_view.confidence, 2),
        simulated_outcome=sim_outcome.outcome,
        simulated_confidence=round(sim_outcome.confidence, 2),
        baseline_impact_score=baseline_view.impact_score,
        simulated_impact_score=simulated_score,
        delta_impact_score=delta,
        resolved_failures=resolved,
        remaining_failures=remaining,
        new_risks=new_risks,
        assumptions=list(verdict.assumptions),
        event_ids=list(baseline_view.event_ids),
        evidence_ids=list(baseline_view.evidence_ids),
        rule_ids=_rule_ids_for(rule, sim_outcome, sim_failure),
        metadata=metadata,
    )


def _rank(results: list[SimulationResult]) -> list[CompareItem]:
    applicable = [result for result in results
                  if result.status == SIM_STATUS_SIMULATED]
    applicable.sort(
        key=lambda result: (
            result.delta_impact_score,
            len(result.remaining_failures),
            len(result.assumptions),
            result.intervention.intervention_type,
        )
    )
    return [
        CompareItem(
            rank=index + 1,
            intervention_type=result.intervention.intervention_type,
            label=result.intervention.label,
            status=result.status,
            simulated_outcome=result.simulated_outcome,
            simulated_impact_score=result.simulated_impact_score,
            delta_impact_score=result.delta_impact_score,
            remaining_failure_count=len(result.remaining_failures),
            assumption_count=len(result.assumptions),
        )
        for index, result in enumerate(applicable)
    ]


def simulate(
    journey,
    integrity,
    evidence,
    consistency,
    outcome,
    failure,
    impact,
    context,
    webhooks,
    cross,
    inventory_facts,
    intervention_type: Optional[str] = None,
) -> Optional[SimulationReport]:
    """Run every intervention (or one) over the analyzed transaction.

    Returns None when the requested intervention type is not in the
    registry (the service turns that into a 400 for POST /run).
    """
    inputs = _build_inputs(journey, outcome, failure, impact, inventory_facts)
    baseline_view = _baseline_view(journey, outcome, failure, impact)

    if intervention_type is not None:
        rule = RULE_BY_INTERVENTION.get(intervention_type)
        if rule is None:
            return None
        rules = [rule]
    else:
        rules = list(SIMULATION_RULES)

    results: list[SimulationResult] = []
    for rule in rules:
        verdict = rule.evaluate(inputs)
        results.append(
            _result_for(
                inputs, rule, verdict, outcome, failure, impact,
                baseline_view, webhooks, context, cross,
            )
        )

    report = SimulationReport(
        transaction_id=journey.transaction_id,
        baseline=baseline_view,
        interventions=results,
    )
    if intervention_type is None:
        report.comparison = _rank(results)
    return report
