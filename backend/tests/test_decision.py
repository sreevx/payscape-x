"""Tests for the Part 8 Decision Agent engine.

Covers the deterministic fallback rule registry, the LLM provider
abstraction + structured-output validation (malformed / hallucinated /
unsupported output must be rejected and fall back), deterministic
confidence, deterministic decision ids and the no-provider path.
"""

import uuid

import pytest

from app.decision.engine import (
    build_context,
    compute_decision_confidence,
    decide,
    decide_for_transaction,
)
from app.decision.llm import (
    DecisionLLMProvider,
    LLMProviderError,
    build_provider,
    parse_llm_json,
    validate_proposal,
)
from app.decision.models import (
    ACTION_DO_NOTHING,
    ACTION_HUMAN_REVIEW,
    ACTION_RECOVER_ROOT_CAUSE,
    ACTION_REFUND_OR_CONTAIN,
    DECISION_CONFIDENCE_CEILING,
    DECISION_CONFIDENCE_FLOOR,
    AlternativeAction,
    DecisionContext,
    DecisionProposal,
    SimulationFact,
)
from app.decision.rules import FALLBACK_RULES, fallback_decision
from app.core.config import Settings


# ---------------------------------------------------------------------------
# Context fixtures
# ---------------------------------------------------------------------------

def _context(**overrides) -> DecisionContext:
    defaults = dict(
        transaction_id="tx-1",
        outcome="FAILED",
        outcome_confidence=0.95,
        primary_reason_code="BUSINESS_FAILURE_MARKERS",
        primary_reason_message="failure markers observed",
        consistency_status="CONSISTENT",
        compound_failure_detected=True,
        compound_failure_severity="HIGH",
        evidence_claims=(
            ("ev-1", "PAYMENT_EVIDENCE", "payment captured", "DIRECT", 1.0),
            ("ev-2", "DELIVERY_EVIDENCE", "delivery failed", "DIRECT", 1.0),
        ),
        evidence_gaps=(),
        contradictions=(),
        failure_chain=(
            ("DELIVERY_FAILED", "DELIVERY", "Delivery failed"),
            ("CUSTOMER_IMPACT", "CUSTOMER", "Customer impact"),
        ),
        root_cause_kinds=("DELIVERY_FAILED",),
        impact_score=83.0,
        impact_scope="SINGLE_TRANSACTION",
        affected_transactions=1,
        simulations=(
            SimulationFact(
                intervention_type="REFUND",
                status="SIMULATED",
                simulation_id="sim-refund",
                simulated_outcome="FAILED",
                delta_impact_score=17.0,
            ),
            SimulationFact(
                intervention_type="DO_NOTHING",
                status="SIMULATED",
                simulation_id="sim-nothing",
                simulated_outcome="FAILED",
                delta_impact_score=0.0,
            ),
        ),
        comparison=(("DO_NOTHING", 1), ("REFUND", 2)),
        payment_captured=True,
        refund_recorded=False,
        customer_impacting=True,
        evidence_confidence=1.0,
        event_ids=("evt-1", "evt-2"),
    )
    defaults.update(overrides)
    return DecisionContext(**defaults)


def _proposal(**overrides) -> DecisionProposal:
    defaults = dict(
        recommended_action=ACTION_HUMAN_REVIEW,
        reason="A concise deterministic reason.",
        evidence_ids=("ev-1",),
        event_ids=("evt-1",),
        simulation_id=None,
        alternatives=(),
    )
    defaults.update(overrides)
    return DecisionProposal(**defaults)


# ---------------------------------------------------------------------------
# Deterministic fallback rules
# ---------------------------------------------------------------------------

class TestFallbackRules:
    def test_registry_is_ordered_and_traceable(self):
        priorities = [rule.priority for rule in FALLBACK_RULES]
        assert priorities == sorted(priorities)
        assert len({rule.rule_id for rule in FALLBACK_RULES}) == len(FALLBACK_RULES)

    def test_fulfilled_do_nothing(self):
        ctx = _context(outcome="FULFILLED", customer_impacting=False,
                       failure_chain=())
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_DO_NOTHING
        assert proposal.fallback_rule_id == "DEC_FULFILLED_DO_NOTHING"

    def test_failed_no_capture_do_nothing(self):
        ctx = _context(payment_captured=False)
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_DO_NOTHING
        assert proposal.fallback_rule_id == "DEC_NO_CAPTURE_DO_NOTHING"

    def test_failed_refund_recorded_do_nothing(self):
        ctx = _context(refund_recorded=True)
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_DO_NOTHING
        assert proposal.fallback_rule_id == "DEC_REFUND_COMPLETE_DO_NOTHING"

    def test_unverifiable_human_review(self):
        ctx = _context(outcome="UNVERIFIABLE", contradictions=(
            ("CAPTURED_AND_FAILED", "RULE", "both recorded"),
        ))
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_HUMAN_REVIEW
        assert proposal.fallback_rule_id == "DEC_UNVERIFIABLE_HUMAN_REVIEW"

    def test_at_risk_human_review(self):
        ctx = _context(outcome="AT_RISK")
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_HUMAN_REVIEW
        assert proposal.fallback_rule_id == "DEC_AT_RISK_HUMAN_REVIEW"

    def test_recoverable_root_cause_recover(self):
        ctx = _context(
            root_cause_kinds=("INVENTORY_ALLOCATION_FAILED",),
            failure_chain=(
                ("INVENTORY_ALLOCATION_FAILED", "INVENTORY", "Allocation failed"),
                ("FULFILLMENT_NOT_CREATED", "FULFILLMENT", "No fulfillment"),
            ),
            customer_impacting=False,
            simulations=(
                SimulationFact(
                    intervention_type="ALTERNATIVE_INVENTORY",
                    status="SIMULATED",
                    simulation_id="sim-alt",
                    simulated_outcome="UNVERIFIABLE",
                    delta_impact_score=-100.0,
                    resolved_failure_kinds=("INVENTORY_ALLOCATION_FAILED",),
                    remaining_failure_kinds=(),
                ),
                SimulationFact(
                    intervention_type="REFUND",
                    status="SIMULATED",
                    simulation_id="sim-refund",
                    simulated_outcome="FAILED",
                    delta_impact_score=0.0,
                ),
            ),
        )
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_RECOVER_ROOT_CAUSE
        assert proposal.fallback_rule_id == "DEC_RECOVERABLE_RECOVER"
        assert proposal.simulation_id == "sim-alt"

    def test_recoverable_root_cause_but_not_effective_falls_through(self):
        # Recovery kind present but the simulation did NOT resolve anything.
        ctx = _context(
            root_cause_kinds=("INVENTORY_ALLOCATION_FAILED",),
            failure_chain=(("INVENTORY_ALLOCATION_FAILED", "INVENTORY", "x"),),
            customer_impacting=False,
            simulations=(
                SimulationFact(
                    intervention_type="ALTERNATIVE_INVENTORY",
                    status="NOT_EFFECTIVE",
                    simulation_id="sim-alt",
                    simulated_outcome="FAILED",
                    delta_impact_score=0.0,
                ),
            ),
        )
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_HUMAN_REVIEW
        assert proposal.fallback_rule_id == "DEC_FAILED_HUMAN_REVIEW"

    def test_customer_impacting_contain(self):
        proposal = fallback_decision(_context())
        assert proposal.recommended_action == ACTION_REFUND_OR_CONTAIN
        assert proposal.fallback_rule_id == "DEC_CUSTOMER_IMPACT_CONTAIN"
        assert proposal.simulation_id == "sim-refund"

    def test_failed_without_remedy_human_review(self):
        ctx = _context(customer_impacting=False, failure_chain=(
            ("INVENTORY_ALLOCATION_FAILED", "INVENTORY", "x"),
        ), simulations=())
        proposal = fallback_decision(ctx)
        assert proposal.recommended_action == ACTION_HUMAN_REVIEW
        assert proposal.fallback_rule_id == "DEC_FAILED_HUMAN_REVIEW"

    def test_fallback_references_verified_ids(self):
        proposal = fallback_decision(_context())
        assert set(proposal.evidence_ids) == {"ev-1", "ev-2"}
        assert set(proposal.event_ids) == {"evt-1", "evt-2"}
        assert all(
            alternative.action in (
                ACTION_DO_NOTHING, ACTION_RECOVER_ROOT_CAUSE,
                ACTION_REFUND_OR_CONTAIN, ACTION_HUMAN_REVIEW,
            )
            for alternative in proposal.alternatives
        )


# ---------------------------------------------------------------------------
# Validation — the code gatekeeper
# ---------------------------------------------------------------------------

class TestProposalValidation:
    def test_valid_proposal_passes(self):
        assert validate_proposal(_proposal(), _context()) == []

    def test_unsupported_action_rejected(self):
        errors = validate_proposal(
            _proposal(recommended_action="SHIP_ROCKET"), _context()
        )
        assert any("unsupported action" in error for error in errors)

    def test_hallucinated_evidence_id_rejected(self):
        errors = validate_proposal(
            _proposal(evidence_ids=("made-up-evidence",)), _context()
        )
        assert any("hallucinated evidence" in error for error in errors)

    def test_hallucinated_event_id_rejected(self):
        errors = validate_proposal(
            _proposal(event_ids=("made-up-event",)), _context()
        )
        assert any("hallucinated event" in error for error in errors)

    def test_unsupported_simulation_rejected(self):
        errors = validate_proposal(
            _proposal(simulation_id="not-a-real-simulation"), _context()
        )
        assert any("unsupported simulation" in error for error in errors)

    def test_empty_reason_rejected(self):
        errors = validate_proposal(_proposal(reason="   "), _context())
        assert any("empty reason" in error for error in errors)

    def test_out_of_bounds_llm_confidence_rejected(self):
        errors = validate_proposal(
            _proposal(llm_confidence=1.5), _context()
        )
        assert any("llm_confidence" in error for error in errors)

    def test_unsupported_alternative_rejected(self):
        errors = validate_proposal(
            _proposal(alternatives=(
                AlternativeAction(action="AUTO_REFUND", reason="x"),
            )),
            _context(),
        )
        assert any("alternative" in error for error in errors)


# ---------------------------------------------------------------------------
# LLM JSON parsing + provider factory
# ---------------------------------------------------------------------------

class TestLLMParsing:
    def test_parse_valid_json(self):
        raw = (
            '{"recommended_action": "HUMAN_REVIEW", "reason": "ok", '
            '"evidence_ids": ["ev-1"], "event_ids": ["evt-1"], '
            '"simulation_id": null, "alternatives": [], '
            '"llm_confidence": 0.7}'
        )
        proposal = parse_llm_json(raw)
        assert proposal.recommended_action == ACTION_HUMAN_REVIEW
        assert proposal.evidence_ids == ("ev-1",)
        assert proposal.llm_confidence == 0.7

    def test_parse_code_fenced_json(self):
        raw = '```json\n{"recommended_action": "DO_NOTHING", "reason": "ok"}\n```'
        proposal = parse_llm_json(raw)
        assert proposal.recommended_action == ACTION_DO_NOTHING

    def test_parse_malformed_raises(self):
        with pytest.raises(LLMProviderError):
            parse_llm_json("this is not json")
        with pytest.raises(LLMProviderError):
            parse_llm_json('[1, 2, 3]')
        with pytest.raises(LLMProviderError):
            parse_llm_json('{"recommended_action": 42}')


class TestProviderFactory:
    def test_default_is_none(self):
        settings = Settings(decision_llm_provider="none")
        assert build_provider(settings) is None

    def test_empty_provider_is_none(self):
        settings = Settings(decision_llm_provider="")
        assert build_provider(settings) is None

    def test_openai_compatible_without_config_is_none(self):
        settings = Settings(decision_llm_provider="openai_compatible")
        assert build_provider(settings) is None

    def test_openai_compatible_configured_builds(self):
        settings = Settings(
            decision_llm_provider="openai_compatible",
            decision_llm_base_url="https://api.example.com/v1",
            decision_llm_model="gpt-4o-mini",
            decision_llm_api_key="k",
        )
        provider = build_provider(settings)
        assert provider is not None
        assert provider.name == "openai_compatible_http"

    def test_unknown_provider_is_none(self):
        settings = Settings(decision_llm_provider="claude-42")
        assert build_provider(settings) is None


# ---------------------------------------------------------------------------
# decide() — provider path, rejection and deterministic fallback
# ---------------------------------------------------------------------------

class _FakeProvider(DecisionLLMProvider):
    def __init__(self, proposal=None, error=None, name="fake"):
        self._proposal = proposal
        self._error = error
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def generate(self, context):
        if self._error is not None:
            raise LLMProviderError(self._error)
        return self._proposal(context) if callable(self._proposal) else self._proposal


class TestDecide:
    def test_no_provider_uses_fallback(self):
        result = decide(_context())
        assert result.decision_source == "DETERMINISTIC_FALLBACK"
        assert result.recommended_action == ACTION_REFUND_OR_CONTAIN
        assert "No LLM provider configured" in result.metadata["provider_note"]

    def test_valid_llm_proposal_accepted(self):
        provider = _FakeProvider(proposal=lambda ctx: _proposal(
            evidence_ids=tuple(sorted(ctx.all_evidence_ids)),
            event_ids=tuple(sorted(ctx.all_event_ids)),
            llm_confidence=0.8,
        ))
        result = decide(_context(), provider=provider)
        assert result.decision_source == "LLM"
        assert result.recommended_action == ACTION_HUMAN_REVIEW
        # LLM confidence is an explanation signal only — never the system
        # confidence.
        assert result.metadata["llm_confidence_signal"] == 0.8
        assert result.decision_confidence == compute_decision_confidence(_context())

    def test_malformed_provider_falls_back(self):
        provider = _FakeProvider(error="boom")
        result = decide(_context(), provider=provider)
        assert result.decision_source == "DETERMINISTIC_FALLBACK"
        assert "LLM provider failed" in result.metadata["provider_note"]

    def test_hallucinated_output_falls_back(self):
        provider = _FakeProvider(proposal=lambda ctx: _proposal(
            evidence_ids=("hallucinated-evidence",)
        ))
        result = decide(_context(), provider=provider)
        assert result.decision_source == "DETERMINISTIC_FALLBACK"
        assert "hallucinated evidence" in result.metadata["provider_note"]

    def test_deterministic_repeated_execution(self):
        ctx = _context()
        first = decide(ctx)
        second = decide(ctx)
        assert first.decision_id == second.decision_id
        assert first.recommended_action == second.recommended_action
        assert first.decision_confidence == second.decision_confidence
        assert first.evidence_ids == second.evidence_ids
        assert first.event_ids == second.event_ids

    def test_decision_id_is_deterministic_uuid5(self):
        result = decide(_context())
        parsed = uuid.UUID(result.decision_id)
        assert parsed.version == 5
        assert result.decision_id == str(
            uuid.uuid5(uuid.NAMESPACE_URL, "payscape:decision:tx-1")
        )

    def test_confidence_bounds(self):
        for outcome, oc in (
            ("FULFILLED", 0.97),
            ("FAILED", 0.95),
            ("AT_RISK", 0.60),
            ("UNVERIFIABLE", 0.35),
        ):
            ctx = _context(outcome=outcome, outcome_confidence=oc)
            confidence = compute_decision_confidence(ctx)
            assert DECISION_CONFIDENCE_FLOOR <= confidence <= DECISION_CONFIDENCE_CEILING

    def test_inconsistent_records_penalty(self):
        consistent = compute_decision_confidence(_context(consistency_status="CONSISTENT"))
        inconsistent = compute_decision_confidence(
            _context(consistency_status="INCONSISTENT")
        )
        assert inconsistent == pytest.approx(consistent - 0.05)

    def test_approval_defaults(self):
        result = decide(_context())
        assert result.approval_status == "PENDING"
        assert result.rejection_reason is None
        assert result.decided_at is None
        assert result.human_approval_required is True
        do_nothing = decide(_context(outcome="FULFILLED", customer_impacting=False))
        assert do_nothing.human_approval_required is False

    def test_assemble_references_verified_ids(self):
        result = decide(_context())
        assert set(result.evidence_ids) == {"ev-1", "ev-2"}
        assert set(result.event_ids) == {"evt-1", "evt-2"}
        assert result.simulation_id == "sim-refund"
        assert result.metadata["labels"]["recommendation"] == "RECOMMENDATION ONLY"


# ---------------------------------------------------------------------------
# build_context over real pipeline outputs (unit-level smoke)
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_build_context_requires_real_shapes(self):
        # A minimal smoke: build_context should raise AttributeError on junk
        # input rather than silently producing an empty context.
        with pytest.raises(AttributeError):
            build_context(None, None, None, None, None, None, None)

    def test_decide_for_transaction_without_provider(self):
        # Guards the service entry-point signature.
        with pytest.raises(AttributeError):
            decide_for_transaction(None, None, None, None, None, None, None)