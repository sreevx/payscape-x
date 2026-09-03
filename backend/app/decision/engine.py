"""Decision Agent engine (Part 8).

Deterministic pipeline for one already-analyzed transaction:

    journey/evidence/consistency/outcome/failure/impact/simulation (Parts 3-7)
        -> DecisionContext (structured, verified facts — the ONLY LLM input)
        -> provider proposal (LLM) OR deterministic fallback rules
        -> validate against the verified context (code gatekeeper)
        -> assemble a fully traceable DecisionResult

Invariants:

- Part 5 remains the sole authority for the outcome classification; Part 6
  for failure/impact; Part 7 for simulation results. This module only reads
  them and never recalculates or mutates them.
- The LLM never invents evidence: every claimed evidence id / event id must
  exist in the verified context, and every simulation reference must be one
  of the simulations that actually ran.
- Invalid, malformed or hallucinating provider output is rejected and the
  deterministic fallback is used. The system works with NO provider.
- decision_confidence is ALWAYS computed deterministically from verified
  inputs. An LLM confidence value is an explanation signal only.
- Nothing here executes an action. Approving a decision (the API layer)
  only records merchant approval.
"""

import uuid
from dataclasses import replace
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.events import EventType
from app.decision.llm import (
    DecisionLLMProvider,
    LLMProviderError,
    build_provider,
    validate_proposal,
)
from app.decision.models import (
    ACTION_DO_NOTHING,
    DECISION_CONFIDENCE_CEILING,
    DECISION_CONFIDENCE_FLOOR,
    APPROVAL_PENDING,
    SOURCE_FALLBACK,
    SOURCE_LLM,
    AlternativeAction,
    DecisionContext,
    DecisionProposal,
    DecisionResult,
    SimulationFact,
)
from app.decision.rules import fallback_decision

NAMESPACE = uuid.NAMESPACE_URL

# Event types that prove a captured payment / a recorded refund / customer
# impact (mirrors the Part 7 vocabulary).
_CAPTURE_TYPES = frozenset({EventType.PAYMENT_CAPTURED.value})
_REFUND_TYPES = frozenset({
    EventType.REFUND_INITIATED.value,
    EventType.REFUND_COMPLETED.value,
    EventType.PAYMENT_REFUNDED.value,
})
_CUSTOMER_IMPACT_TYPES = frozenset({
    EventType.CUSTOMER_COMPLAINT.value,
    EventType.CUSTOMER_MESSAGE_RECEIVED.value,
    EventType.DELIVERY_FAILED.value,
    EventType.DELIVERY_RETURNED.value,
})
_CUSTOMER_STAGES = frozenset({"DELIVERY", "CUSTOMER", "REFUND"})


def _event_types(journey) -> frozenset[str]:
    return frozenset(
        event.event_type for event in journey.chronological_events
    )


def _evidence_confidence(
    context: DecisionContext,
    supporting_evidence_ids: frozenset[str],
) -> float:
    """Mean confidence of the supporting evidence items (deterministic).

    Falls back to the outcome confidence when no evidence is referenced.
    """
    claims = {item[0]: item[4] for item in context.evidence_claims}
    picked = [claims[eid] for eid in supporting_evidence_ids if eid in claims]
    if not picked:
        return context.outcome_confidence
    return round(sum(picked) / len(picked), 3)


def build_context(
    journey,
    evidence,
    consistency,
    outcome,
    failure,
    impact,
    simulation_report,
) -> DecisionContext:
    """Build the structured, verified facts from the Parts 3-7 outputs."""
    event_types = _event_types(journey)
    event_ids = tuple(
        sorted(event.event_id for event in journey.chronological_events)
    )

    evidence_claims = tuple(
        (item.evidence_id, item.category, item.claim, item.strength,
         round(float(item.confidence), 3))
        for item in evidence.evidence
    )
    evidence_gaps = tuple(
        (gap.event_type, gap.note) for gap in evidence.gaps
    )
    contradictions = tuple(
        (contradiction.type, contradiction.rule_id, contradiction.explanation)
        for contradiction in evidence.contradictions
    )
    failure_chain = tuple(
        (node.kind, node.stage, node.label)
        for node in failure.failure_chain
    )
    root_cause_kinds = tuple(
        sorted({root.kind for root in failure.root_causes})
    )

    simulations = tuple(
        SimulationFact(
            intervention_type=item.intervention.intervention_type,
            status=item.status,
            simulation_id=item.simulation_id,
            simulated_outcome=item.simulated_outcome,
            delta_impact_score=round(float(item.delta_impact_score), 3),
            resolved_failure_kinds=tuple(
                sorted({ref.kind for ref in item.resolved_failures})
            ),
            remaining_failure_kinds=tuple(
                sorted({ref.kind for ref in item.remaining_failures})
            ),
        )
        for item in simulation_report.interventions
    )
    comparison = tuple(
        (row.intervention_type, int(row.rank))
        for row in simulation_report.comparison
    )

    customer_impacting = bool(
        {node[1] for node in failure_chain} & _CUSTOMER_STAGES
        or event_types & _CUSTOMER_IMPACT_TYPES
    )

    ctx = DecisionContext(
        transaction_id=journey.transaction_id,
        outcome=outcome.outcome,
        outcome_confidence=round(float(outcome.confidence), 3),
        primary_reason_code=outcome.primary_reason.code,
        primary_reason_message=outcome.primary_reason.message,
        consistency_status=consistency.overall_integrity,
        compound_failure_detected=failure.detected,
        compound_failure_severity=failure.severity,
        evidence_claims=evidence_claims,
        evidence_gaps=evidence_gaps,
        contradictions=contradictions,
        failure_chain=failure_chain,
        root_cause_kinds=root_cause_kinds,
        impact_score=round(float(impact.impact_score), 3),
        impact_scope=impact.scope,
        affected_transactions=int(impact.affected_transactions),
        simulations=simulations,
        comparison=comparison,
        payment_captured=bool(event_types & _CAPTURE_TYPES),
        refund_recorded=bool(event_types & _REFUND_TYPES),
        customer_impacting=customer_impacting,
        evidence_confidence=0.0,
        event_ids=event_ids,
    )
    supporting = frozenset(outcome.supporting_evidence_ids)
    return replace(ctx, evidence_confidence=_evidence_confidence(ctx, supporting))


def compute_decision_confidence(ctx: DecisionContext) -> float:
    """Deterministic, bounded decision confidence from verified inputs.

    Formula (documented in docs/architecture.md):

        0.65 * outcome_confidence
      + 0.35 * evidence_confidence
      - 0.05  if records are internally inconsistent

    clamped to [DECISION_CONFIDENCE_FLOOR, DECISION_CONFIDENCE_CEILING].
    Never taken from the LLM.
    """
    raw = (
        0.65 * ctx.outcome_confidence
        + 0.35 * ctx.evidence_confidence
        - (0.05 if ctx.consistency_status == "INCONSISTENT" else 0.0)
    )
    return round(
        max(DECISION_CONFIDENCE_FLOOR, min(DECISION_CONFIDENCE_CEILING, raw)),
        3,
    )


def _decision_id(transaction_id: str) -> str:
    return str(
        uuid.uuid5(NAMESPACE, f"payscape:decision:{transaction_id}")
    )


def assemble(
    ctx: DecisionContext,
    proposal: DecisionProposal,
    source: str,
    provider_note: Optional[str] = None,
) -> DecisionResult:
    """Assemble the auditable DecisionResult from a validated proposal."""
    decision_confidence = compute_decision_confidence(ctx)
    alternatives = [
        AlternativeAction(action=item.action, reason=item.reason)
        for item in proposal.alternatives
    ]
    metadata: dict = {
        "outcome": ctx.outcome,
        "outcome_confidence": ctx.outcome_confidence,
        "consistency_status": ctx.consistency_status,
        "compound_failure_detected": ctx.compound_failure_detected,
        "impact_score": ctx.impact_score,
        "fallback_rule_id": proposal.fallback_rule_id,
        "evidence_confidence": ctx.evidence_confidence,
        "labels": {"recommendation": "RECOMMENDATION ONLY",
                   "approval": "RECORDS APPROVAL ONLY — NEVER EXECUTES"},
    }
    if provider_note:
        metadata["provider_note"] = provider_note
    if proposal.llm_confidence is not None:
        metadata["llm_confidence_signal"] = proposal.llm_confidence

    return DecisionResult(
        decision_id=_decision_id(ctx.transaction_id),
        transaction_id=ctx.transaction_id,
        decision_source=source,
        recommended_action=proposal.recommended_action,
        reason=proposal.reason,
        decision_confidence=decision_confidence,
        evidence_confidence=ctx.evidence_confidence,
        evidence_ids=sorted(set(proposal.evidence_ids)),
        event_ids=sorted(set(proposal.event_ids)),
        simulation_id=proposal.simulation_id,
        alternatives=alternatives,
        human_approval_required=proposal.recommended_action != ACTION_DO_NOTHING,
        approval_status=APPROVAL_PENDING,
        rejection_reason=None,
        decided_at=None,
        created_at=None,
        updated_at=None,
        metadata=metadata,
    )


def decide(
    ctx: DecisionContext,
    provider: Optional[DecisionLLMProvider] = None,
    provider_note: Optional[str] = None,
) -> DecisionResult:
    """Produce the decision: validated LLM proposal or deterministic fallback.

    - With a provider: any failure (LLMProviderError) or validation error
      discards the output and uses the deterministic fallback, recording
      why in metadata.
    - Without a provider: the deterministic fallback runs automatically.
    """
    source = SOURCE_FALLBACK
    proposal: Optional[DecisionProposal] = None
    note = provider_note

    if provider is not None:
        try:
            candidate = provider.generate(ctx)
        except LLMProviderError as exc:
            note = (note + "; " if note else "") + f"LLM provider failed: {exc}"
        else:
            errors = validate_proposal(candidate, ctx)
            if errors:
                note = (
                    (note + "; " if note else "")
                    + "Rejected LLM output: "
                    + "; ".join(errors)
                )
            else:
                proposal = candidate
                source = SOURCE_LLM

    if proposal is None:
        proposal = fallback_decision(ctx)
        if provider is None:
            note = (note + "; " if note else "") + (
                "No LLM provider configured — deterministic fallback used."
            )
        elif source != SOURCE_LLM:
            note = (note + "; " if note else "") + (
                "Deterministic fallback used instead of the rejected LLM "
                "output."
            )

    return assemble(ctx, proposal, source, provider_note=note)


def decide_for_transaction(
    journey,
    evidence,
    consistency,
    outcome,
    failure,
    impact,
    simulation_report,
    provider: Optional[DecisionLLMProvider] = None,
    provider_note: Optional[str] = None,
) -> DecisionResult:
    """Convenience: build the context then decide (used by the service)."""
    ctx = build_context(
        journey, evidence, consistency, outcome, failure, impact,
        simulation_report,
    )
    return decide(ctx, provider=provider, provider_note=provider_note)


def configured_provider(settings: Optional[Settings] = None):
    """Provider from the environment (None -> deterministic fallback)."""
    return build_provider(settings or get_settings())