"""Outcome decision engine (Part 5).

Deterministically classifies one reconstructed transaction into exactly one
of FULFILLED / AT_RISK / FAILED / UNVERIFIABLE.

Decision process (documented in docs/architecture.md):

    journey + evidence + consistency
        -> run OUTCOME_RULES in fixed priority order
        -> first match decides the primary outcome + primary reason
        -> later matches that AGREE with the outcome add corroborating
           reasons (so compound chains surface every failure branch)
        -> later matches with a DIFFERENT outcome are recorded in the trace
           as overridden — never silently ignored
        -> confidence = deterministic base - documented adjustments
        -> evidence_completeness = observed downstream lifecycle groups

The engine never says "payment succeeded, therefore FULFILLED": FULFILLED is
only reachable via a delivery-completed record, and FAILED is decided from
business records (markers, delivery, cancellation, allocation), not from the
payment status alone.

Confidence methodology (deterministic, auditable):

    base = OUTCOME_BASE_CONFIDENCE[outcome]   (UNVERIFIABLE caused by a
           contradiction uses UNVERIFIABLE_CONTRADICTION_CONFIDENCE)
    then each documented adjustment is subtracted when its signal exists:

      - DELAYED_WEBHOOK        integrity.delayed_events present      -0.05
      - OUT_OF_ORDER_EVENTS    integrity.out_of_order_events present -0.05
      - CONSISTENCY_VIOLATION  per consistency violation              -0.10
                               (only for non-UNVERIFIABLE outcomes —
                                the UNVERIFIABLE base already reflects
                                the lack of certainty)
      - CONTRADICTED_EVIDENCE  per CONTRADICTED evidence item         -0.10
                               (only for non-UNVERIFIABLE outcomes —
                                e.g. a delivery contradiction resolved
                                by a later successful delivery)

    confidence = clamp(base + adjustments, CONFIDENCE_FLOOR, CEILING),
    rounded to two decimals. Confidence is a deterministic record-strength
    score — it is NOT a statistical probability and NOT fake certainty.
"""

from typing import Optional

from app.consistency.models import ConsistencyResult, STATUS_VIOLATION
from app.evidence.models import (
    STRENGTH_CONTRADICTED,
    STRENGTH_CORROBORATED,
    STRENGTH_DIRECT,
    EvidenceReport,
)
from app.journey.integrity import JourneyIntegrity
from app.journey.reconstructor import ReconstructedJourney
from app.outcome.models import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    OUTCOME_AT_RISK,
    OUTCOME_BASE_CONFIDENCE,
    OUTCOME_UNVERIFIABLE,
    UNVERIFIABLE_CONTRADICTION_CONFIDENCE,
    ConfidenceAdjustment,
    OutcomeResult,
    RuleTraceStep,
)
from app.outcome.rules import (
    COMPLETENESS_GROUPS,
    OUTCOME_RULES,
    build_context,
)


def _evidence_for_events(
    evidence: EvidenceReport,
    event_ids: set[str],
    strengths: frozenset[str],
) -> list[str]:
    """Evidence ids of items that reference any of the given events."""
    return sorted(
        {
            item.evidence_id
            for item in evidence.evidence
            if item.strength in strengths and set(item.event_ids) & event_ids
        }
    )


def _contradicted_evidence_ids(evidence: EvidenceReport) -> list[str]:
    return sorted(
        item.evidence_id
        for item in evidence.evidence
        if item.strength == STRENGTH_CONTRADICTED
    )


def _missing_evidence_ids(evidence: EvidenceReport) -> list[str]:
    from app.evidence.models import STRENGTH_MISSING

    return sorted(
        item.evidence_id
        for item in evidence.evidence
        if item.strength == STRENGTH_MISSING
    )


def _evidence_completeness(
    journey: ReconstructedJourney, present_types: set[str]
) -> Optional[float]:
    """Fraction (0..1) of the five post-payment lifecycle groups that carry
    observed evidence — positive or explicit-negative. None when the payment
    was never captured (downstream groups are not applicable)."""
    from app.core.events import EventType

    if EventType.PAYMENT_CAPTURED.value not in present_types:
        return None
    observed = sum(
        1 for _name, group in COMPLETENESS_GROUPS if group & present_types
    )
    return round(observed / len(COMPLETENESS_GROUPS), 2)


def _matches_of_rule(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    evidence: EvidenceReport,
    consistency: ConsistencyResult,
) -> tuple:
    """Run every rule in priority order.

    Returns (primary_rule, primary_match, corroborating_rules,
    corroborating_matches) where corroborating items are later rules whose
    outcome agrees with the primary outcome.
    """
    ctx = build_context(journey, integrity, evidence, consistency)
    primary_rule = None
    primary_match = None
    corroborating: list[tuple] = []
    for rule in OUTCOME_RULES:
        match = rule.evaluate(ctx)
        if match is None:
            continue
        if primary_rule is None:
            primary_rule = rule
            primary_match = match
            continue
        if rule.outcome == primary_rule.outcome:
            corroborating.append((rule, match))
    return ctx, primary_rule, primary_match, corroborating


def _apply_confidence(
    ctx,
    outcome: str,
    primary_rule,
) -> tuple[float, list[ConfidenceAdjustment]]:
    """Deterministic confidence with a fully traced adjustment list."""
    contradicted = _contradicted_evidence_ids(ctx.evidence)
    violation_count = len(ctx.consistency.violations)
    if outcome == OUTCOME_UNVERIFIABLE and primary_rule.rule_id == "CRITICAL_CONTRADICTION":
        base = UNVERIFIABLE_CONTRADICTION_CONFIDENCE
    else:
        base = OUTCOME_BASE_CONFIDENCE[outcome]

    adjustments: list[ConfidenceAdjustment] = []
    if ctx.integrity.delayed_events:
        adjustments.append(
            ConfidenceAdjustment(
                signal="DELAYED_WEBHOOK",
                delta=-0.05,
                note="a webhook delivery was flagged delayed",
            )
        )
    if ctx.integrity.out_of_order_events:
        adjustments.append(
            ConfidenceAdjustment(
                signal="OUT_OF_ORDER_EVENTS",
                delta=-0.05,
                note="event ingestion order differs from chronological order",
            )
        )
    if outcome != OUTCOME_UNVERIFIABLE:
        if contradicted:
            for item_id in contradicted:
                adjustments.append(
                    ConfidenceAdjustment(
                        signal="CONTRADICTED_EVIDENCE",
                        delta=-0.10,
                        note=f"contradictory evidence item {item_id}",
                    )
                )
        if violation_count:
            for rule_id in sorted(ctx.consistency.violations):
                adjustments.append(
                    ConfidenceAdjustment(
                        signal="CONSISTENCY_VIOLATION",
                        delta=-0.10,
                        note=f"consistency rule {rule_id} violated",
                    )
                )

    total = base + sum(adjustment.delta for adjustment in adjustments)
    confidence = round(
        min(CONFIDENCE_CEILING, max(CONFIDENCE_FLOOR, total)), 2
    )
    return confidence, adjustments


def decide(
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
    evidence: EvidenceReport,
    consistency: ConsistencyResult,
) -> OutcomeResult:
    """Classify one journey into a deterministic OutcomeResult."""
    ctx, primary_rule, primary_match, corroborating = _matches_of_rule(
        journey, integrity, evidence, consistency
    )
    if primary_rule is None or primary_match is None:  # pragma: no cover
        # Every captured/failed/unresolved payment is covered by the rules,
        # so this cannot happen; kept as a defensive guard.
        raise RuntimeError("outcome rules produced no classification")

    # Primary reason ids.
    involved_event_ids = set(primary_match.reason.event_ids)
    supporting_evidence_ids = _evidence_for_events(
        evidence, involved_event_ids, frozenset({STRENGTH_DIRECT, STRENGTH_CORROBORATED})
    )

    # Every reason carries the evidence items that directly support its own
    # events — full evidence traceability per reason.
    primary_match.reason.evidence_ids = _evidence_for_events(
        evidence, set(primary_match.reason.event_ids),
        frozenset({STRENGTH_DIRECT, STRENGTH_CORROBORATED}),
    )

    reasons = [primary_match.reason]
    rule_trace = []
    applied_rules: list[tuple] = [(primary_rule, primary_match, True)]

    # Rules evaluated later that agree add corroborating reasons; rules that
    # disagree are overridden but recorded in the trace.
    for rule, match in corroborating:
        match.reason.evidence_ids = _evidence_for_events(
            evidence, set(match.reason.event_ids),
            frozenset({STRENGTH_DIRECT, STRENGTH_CORROBORATED}),
        )
        reasons.append(match.reason)
        applied_rules.append((rule, match, True))
        involved_event_ids.update(match.reason.event_ids)
        supporting_evidence_ids.extend(
            _evidence_for_events(
                evidence,
                set(match.reason.event_ids),
                frozenset({STRENGTH_DIRECT, STRENGTH_CORROBORATED}),
            )
        )

    for rule in OUTCOME_RULES:
        applied = any(rule.rule_id == applied_rule.rule_id for applied_rule, _, _ in applied_rules)
        if applied:
            trace_note = "fired"
        elif rule.priority > primary_rule.priority:
            trace_note = "not applied — outcome overridden by a higher-priority rule"
        else:
            trace_note = "not applied — preconditions not met"
        rule_trace.append(
            RuleTraceStep(
                rule_id=rule.rule_id,
                name=rule.name,
                priority=rule.priority,
                outcome=rule.outcome,
                applied=applied,
                note=trace_note,
            )
        )

    supporting_evidence_ids = sorted(set(supporting_evidence_ids))
    supporting_event_ids = sorted(involved_event_ids)

    # Blocking evidence: contradicted records always block certainty; missing
    # critical evidence blocks UNVERIFIABLE / AT_RISK classifications.
    blocking_evidence_ids = _contradicted_evidence_ids(evidence)
    if primary_rule.outcome in (OUTCOME_UNVERIFIABLE, OUTCOME_AT_RISK):
        blocking_evidence_ids.extend(_missing_evidence_ids(evidence))
    blocking_evidence_ids = sorted(set(blocking_evidence_ids))

    completeness = _evidence_completeness(ctx.journey, ctx.present_types)
    confidence, adjustments = _apply_confidence(ctx, primary_rule.outcome, primary_rule)

    return OutcomeResult(
        transaction_id=journey.transaction_id,
        outcome=primary_rule.outcome,
        confidence=confidence,
        primary_reason=primary_match.reason,
        reasons=reasons,
        supporting_evidence_ids=supporting_evidence_ids,
        supporting_event_ids=supporting_event_ids,
        blocking_evidence_ids=blocking_evidence_ids,
        consistency_status=ctx.consistency.overall_integrity,
        evidence_completeness=completeness,
        rule_trace=rule_trace,
        confidence_adjustments=adjustments,
    )