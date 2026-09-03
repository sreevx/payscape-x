"""Deterministic fallback rule registry (Part 8).

The Decision Agent MUST work without any LLM provider. This registry is the
mandatory deterministic fallback: it picks a recommended action from the
closed registry using ONLY verified facts from the DecisionContext.

Rule semantics (priority order — the first applicable rule wins):

1. DEC_FULFILLED_DO_NOTHING      outcome FULFILLED            -> DO_NOTHING
2. DEC_UNVERIFIABLE_HUMAN_REVIEW outcome UNVERIFIABLE         -> HUMAN_REVIEW
3. DEC_AT_RISK_HUMAN_REVIEW      outcome AT_RISK              -> HUMAN_REVIEW
4. DEC_NO_CAPTURE_DO_NOTHING     FAILED, no capture           -> DO_NOTHING
5. DEC_REFUND_COMPLETE_DO_NOTHING FAILED, refund recorded     -> DO_NOTHING
6. DEC_RECOVERABLE_RECOVER       FAILED, recoverable root
                                 cause AND a Part 7 recovery
                                 simulation actually resolves
                                 a failure                     -> RECOVER_ROOT_CAUSE
7. DEC_CUSTOMER_IMPACT_CONTAIN   FAILED, captured, no refund,
                                 customer-impacting failure
                                 AND the refund simulation is
                                 SIMULATED                     -> REFUND_OR_CONTAIN
8. DEC_FAILED_HUMAN_REVIEW       FAILED without any justified
                                 recovery or containment       -> HUMAN_REVIEW

The registry never invents recovery: rule 6 fires only when the real
simulation resolved at least one failure node. Rule 7 is containment, not
a delivery fix — the reason always states that a refund does not deliver
the goods. Rule 8 is the honest "no deterministic remedy is justified"
answer rather than a guessed action.

Every rule exposes its rule_id so the assembled decision is fully
traceable. The same context always produces the same action.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from app.decision.models import (
    ACTION_DO_NOTHING,
    ACTION_HUMAN_REVIEW,
    ACTION_RECOVER_ROOT_CAUSE,
    ACTION_REFUND_OR_CONTAIN,
    RECOVERABLE_ROOT_CAUSE_KINDS,
    RECOVERY_INTERVENTIONS,
    AlternativeAction,
    DecisionContext,
    DecisionProposal,
)

# Deterministic one-line reasons for each alternative (same wording every
# time — no free-form LLM prose in the fallback).
_ALT_REASONS: dict[str, str] = {
    ACTION_DO_NOTHING: "Take no action and leave the records untouched.",
    ACTION_RECOVER_ROOT_CAUSE: (
        "Attempt to recover the recorded root cause once its "
        "deterministic prerequisites are met."
    ),
    ACTION_REFUND_OR_CONTAIN: (
        "Contain the customer impact with a refund — containment never "
        "fixes fulfillment or delivery."
    ),
    ACTION_HUMAN_REVIEW: (
        "Escalate to human operations for manual investigation and decision."
    ),
}


def _alternative(action: str) -> AlternativeAction:
    return AlternativeAction(action=action, reason=_ALT_REASONS[action])


def _other_actions(except_action: str) -> tuple[AlternativeAction, ...]:
    return tuple(
        _alternative(action)
        for action in ALL_ACTIONS_ORDER
        if action != except_action
    )


# Registry order (display + fallback alternative order).
ALL_ACTIONS_ORDER = (
    ACTION_DO_NOTHING,
    ACTION_RECOVER_ROOT_CAUSE,
    ACTION_REFUND_OR_CONTAIN,
    ACTION_HUMAN_REVIEW,
)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _rule_fulfilled(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "FULFILLED":
        return None
    return DecisionProposal(
        recommended_action=ACTION_DO_NOTHING,
        reason=(
            "The business outcome is FULFILLED and the records are "
            "consistent with delivery. There is nothing to recover, contain "
            "or escalate — no action is deterministically justified."
        ),
        alternatives=_other_actions(ACTION_DO_NOTHING),
    )


def _rule_unverifiable(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "UNVERIFIABLE":
        return None
    gaps = "; ".join(
        f"{event_type} ({note})" for event_type, note in ctx.evidence_gaps
    )
    contradiction_note = (
        " The records contradict each other, so no deterministic action "
        "is justified."
        if ctx.contradictions
        else " Key records are missing, so no deterministic action is justified."
    )
    reason = (
        "The outcome is UNVERIFIABLE: the evidence is insufficient"
        f"{' (gaps: ' + gaps + ')' if gaps else ''}.{contradiction_note} "
        "A human must investigate before any action is taken."
    )
    return DecisionProposal(
        recommended_action=ACTION_HUMAN_REVIEW,
        reason=reason,
        alternatives=_other_actions(ACTION_HUMAN_REVIEW),
    )


def _rule_at_risk(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "AT_RISK":
        return None
    return DecisionProposal(
        recommended_action=ACTION_HUMAN_REVIEW,
        reason=(
            "The outcome is AT_RISK: the records do not yet prove a "
            "definitive failure, so no recovery or refund is deterministically "
            "justified. Escalate to human operations for review."
        ),
        alternatives=_other_actions(ACTION_HUMAN_REVIEW),
    )


def _rule_no_capture(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "FAILED" or ctx.payment_captured:
        return None
    return DecisionProposal(
        recommended_action=ACTION_DO_NOTHING,
        reason=(
            "The business outcome is FAILED but no payment was captured — "
            "no funds moved and there is nothing to recover or refund. "
            "No downstream action is deterministically justified."
        ),
        alternatives=_other_actions(ACTION_DO_NOTHING),
    )


def _rule_refund_complete(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "FAILED" or not ctx.refund_recorded:
        return None
    return DecisionProposal(
        recommended_action=ACTION_DO_NOTHING,
        reason=(
            "A refund is already recorded for this payment: customer "
            "containment is complete. Re-refunding or re-shipping is not "
            "deterministically justified from the records."
        ),
        alternatives=_other_actions(ACTION_DO_NOTHING),
    )


def _recovery_candidate(ctx: DecisionContext) -> Optional[tuple[str, str]]:
    """Best recovery intervention that deterministically resolved failures.

    Returns (intervention_type, simulation_id) or None. Only interventions
    whose simulation is SIMULATED AND resolved at least one failure node
    count.
    """
    for intervention in RECOVERY_INTERVENTIONS:
        for fact in ctx.simulations:
            if fact.intervention_type != intervention:
                continue
            if fact.status != "SIMULATED":
                continue
            if not fact.resolved_failure_kinds:
                continue
            return intervention, fact.simulation_id
    return None


def _rule_recoverable(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if not (set(ctx.root_cause_kinds) & RECOVERABLE_ROOT_CAUSE_KINDS):
        return None
    candidate = _recovery_candidate(ctx)
    if candidate is None:
        return None
    intervention, simulation_id = candidate
    resolved = ", ".join(sorted(ctx.root_cause_kinds))
    return DecisionProposal(
        recommended_action=ACTION_RECOVER_ROOT_CAUSE,
        reason=(
            "The root cause is recoverable and the Part 7 simulation for "
            f"{intervention} deterministically resolves it (root cause(s): "
            f"{resolved}). Recovery is recommended before containment."
        ),
        simulation_id=simulation_id,
        alternatives=_other_actions(ACTION_RECOVER_ROOT_CAUSE),
    )


def _rule_customer_impact_contain(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "FAILED":
        return None
    if not ctx.payment_captured or ctx.refund_recorded:
        return None
    if not ctx.customer_impacting:
        return None
    refund = next(
        (fact for fact in ctx.simulations if fact.intervention_type == "REFUND"),
        None,
    )
    if refund is None or refund.status != "SIMULATED":
        return None
    return DecisionProposal(
        recommended_action=ACTION_REFUND_OR_CONTAIN,
        reason=(
            "A customer-impacting failure is recorded (delivery/customer "
            "stage) and the refund simulation is applicable. Refund "
            "containment returns the captured amount and replaces the "
            "potential dispute risk — it does not deliver the goods, and "
            "the business outcome remains FAILED in the simulation."
        ),
        simulation_id=refund.simulation_id,
        alternatives=_other_actions(ACTION_REFUND_OR_CONTAIN),
    )


def _rule_failed_human_review(ctx: DecisionContext) -> Optional[DecisionProposal]:
    if ctx.outcome != "FAILED":
        return None
    return DecisionProposal(
        recommended_action=ACTION_HUMAN_REVIEW,
        reason=(
            "The business outcome is FAILED but no deterministic recovery "
            "or containment is justified by the records (no effective "
            "remedy was simulated and/or no customer-impacting failure was "
            "recorded). Escalate to human operations."
        ),
        alternatives=_other_actions(ACTION_HUMAN_REVIEW),
    )


@dataclass(frozen=True)
class DecisionRule:
    """One entry of the deterministic fallback registry."""

    rule_id: str
    name: str
    description: str
    priority: int
    evaluate: Callable[[DecisionContext], Optional[DecisionProposal]]


FALLBACK_RULES: tuple[DecisionRule, ...] = (
    DecisionRule(
        "DEC_FULFILLED_DO_NOTHING",
        "Fulfilled outcome — do nothing",
        "A FULFILLED outcome with consistent records justifies no action.",
        10,
        _rule_fulfilled,
    ),
    DecisionRule(
        "DEC_UNVERIFIABLE_HUMAN_REVIEW",
        "Unverifiable outcome — human review",
        "Insufficient or contradictory evidence justifies no deterministic "
        "action; escalate to a human.",
        20,
        _rule_unverifiable,
    ),
    DecisionRule(
        "DEC_AT_RISK_HUMAN_REVIEW",
        "At-risk outcome — human review",
        "An AT_RISK outcome is not a definitive failure; escalate to a "
        "human rather than guessing.",
        30,
        _rule_at_risk,
    ),
    DecisionRule(
        "DEC_NO_CAPTURE_DO_NOTHING",
        "Failed without capture — do nothing",
        "A FAILED outcome with no captured payment leaves nothing to "
        "recover or refund.",
        40,
        _rule_no_capture,
    ),
    DecisionRule(
        "DEC_REFUND_COMPLETE_DO_NOTHING",
        "Refund already recorded — do nothing",
        "A FAILED outcome with a recorded refund has complete containment.",
        50,
        _rule_refund_complete,
    ),
    DecisionRule(
        "DEC_RECOVERABLE_RECOVER",
        "Recoverable root cause — recover",
        "A FAILED outcome whose root cause the Part 7 simulation "
        "deterministically resolves warrants recovery.",
        60,
        _rule_recoverable,
    ),
    DecisionRule(
        "DEC_CUSTOMER_IMPACT_CONTAIN",
        "Customer-impacting failure — refund / contain",
        "A captured, unrefunded FAILED outcome with customer impact "
        "warrants refund containment when the simulation is applicable.",
        70,
        _rule_customer_impact_contain,
    ),
    DecisionRule(
        "DEC_FAILED_HUMAN_REVIEW",
        "Failed without justified remedy — human review",
        "A FAILED outcome with no deterministic recovery or containment "
        "justified by the records goes to human operations.",
        80,
        _rule_failed_human_review,
    ),
)


def fallback_decision(ctx: DecisionContext) -> DecisionProposal:
    """Deterministic fallback: first applicable rule wins.

    The registry is exhaustive for the four outcomes, so this always
    returns a proposal.
    """
    for rule in FALLBACK_RULES:
        proposal = rule.evaluate(ctx)
        if proposal is not None:
            return DecisionProposal(
                recommended_action=proposal.recommended_action,
                reason=proposal.reason,
                evidence_ids=tuple(sorted(ctx.all_evidence_ids)),
                event_ids=tuple(sorted(ctx.all_event_ids)),
                simulation_id=proposal.simulation_id,
                alternatives=proposal.alternatives,
                fallback_rule_id=rule.rule_id,
            )
    raise AssertionError("fallback registry is exhaustive — unreachable")