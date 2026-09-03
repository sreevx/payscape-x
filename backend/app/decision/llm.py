"""LLM provider abstraction + structured-output validation (Part 8).

Design (AI reasons, CODE VERIFIES):

- `DecisionLLMProvider` is the abstract contract. No other module depends on
  a concrete provider, so real providers (OpenAI-compatible endpoints,
  Razorpay's future assistant, etc.) can be added behind the same interface.
- `HttpDecisionLLMProvider` is a minimal OpenAI-compatible chat-completions
  implementation using only the standard library (`urllib`), activated when
  `DECISION_LLM_PROVIDER` names it. It instructs the model to return strict
  JSON matching the DecisionProposal shape and turns ANY failure (network,
  timeout, malformed JSON, wrong types) into an `LLMProviderError`.
- `build_provider()` reads the environment. When no provider is configured
  the factory returns None and the service uses the mandatory deterministic
  fallback — the system must work without any API key.
- `validate_proposal()` is the code-side gatekeeper: the LLM may only pick
  a registered action, may only reference evidence ids / event ids that
  exist in the verified context, may only reference a simulation that
  actually ran, and must return a concise non-empty reason. Anything else is
  rejected and the deterministic fallback takes over. The LLM never decides
  its own confidence — `llm_confidence` (if present) is kept as an
  explanation signal only and is never used as the system confidence.
"""

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from app.core.config import Settings, get_settings
from app.decision.models import (
    ALL_ACTIONS,
    AlternativeAction,
    DecisionContext,
    DecisionProposal,
)

# Upper bound for the model's reason string — a concise rationale, never a
# hidden chain-of-thought dump.
MAX_REASON_LENGTH = 1200
MAX_ALTERNATIVES = 4
MAX_REFERENCE_IDS = 200


class LLMProviderError(Exception):
    """Raised when a provider fails or returns unusable output."""


class DecisionLLMProvider(ABC):
    """Contract every decision provider (LLM or otherwise) must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier recorded in the audit trail."""

    @abstractmethod
    def generate(self, context: DecisionContext) -> DecisionProposal:
        """Return a structured proposal for the verified context.

        Raises LLMProviderError on ANY failure (network, timeout, malformed
        or invalid output). The caller validates the proposal against the
        context before trusting it.
        """


# ---------------------------------------------------------------------------
# Validation — the code-side gatekeeper
# ---------------------------------------------------------------------------

def validate_proposal(
    proposal: DecisionProposal, context: DecisionContext
) -> list[str]:
    """Return a list of validation errors (empty == acceptable).

    Never trust invalid output: each error below causes the caller to
    discard the proposal and use the deterministic fallback.
    """
    errors: list[str] = []
    if proposal.recommended_action not in ALL_ACTIONS:
        errors.append(
            f"unsupported action {proposal.recommended_action!r} — only "
            f"{', '.join(ALL_ACTIONS)} are allowed"
        )
    reason = proposal.reason or ""
    if not reason.strip():
        errors.append("empty reason")
    elif len(reason) > MAX_REASON_LENGTH:
        errors.append(f"reason exceeds {MAX_REASON_LENGTH} characters")

    if len(proposal.evidence_ids) > MAX_REFERENCE_IDS:
        errors.append("too many evidence ids")
    else:
        unknown_evidence = sorted(
            set(proposal.evidence_ids) - context.all_evidence_ids
        )
        if unknown_evidence:
            errors.append(
                "hallucinated evidence ids: " + ", ".join(unknown_evidence)
            )

    if len(proposal.event_ids) > MAX_REFERENCE_IDS:
        errors.append("too many event ids")
    else:
        unknown_events = sorted(set(proposal.event_ids) - context.all_event_ids)
        if unknown_events:
            errors.append("hallucinated event ids: " + ", ".join(unknown_events))

    if proposal.simulation_id is not None:
        if proposal.simulation_id not in context.simulation_ids:
            errors.append(
                f"unsupported simulation reference {proposal.simulation_id}"
            )

    if len(proposal.alternatives) > MAX_ALTERNATIVES:
        errors.append(f"more than {MAX_ALTERNATIVES} alternatives")
    else:
        for alternative in proposal.alternatives:
            if alternative.action not in ALL_ACTIONS:
                errors.append(
                    f"unsupported alternative action {alternative.action!r}"
                )
                break

    if proposal.llm_confidence is not None:
        try:
            value = float(proposal.llm_confidence)
        except (TypeError, ValueError):
            errors.append("llm_confidence is not numeric")
        else:
            if not (0.0 <= value <= 1.0):
                errors.append("llm_confidence out of [0, 1] bounds")
    return errors


# ---------------------------------------------------------------------------
# OpenAI-compatible HTTP provider (stdlib only — no new dependencies)
# ---------------------------------------------------------------------------

_JSON_PROMPT = """You are the PAYSCAPE-X Decision Agent. You reason ONLY over
the verified facts provided below. You NEVER invent evidence, events,
amounts, customers or simulation results. You NEVER change the outcome,
failure or impact classifications. You only recommend an action from the
closed registry: DO_NOTHING, RECOVER_ROOT_CAUSE, REFUND_OR_CONTAIN,
HUMAN_REVIEW.

Respond with STRICT JSON only (no markdown fences, no commentary) in exactly
this shape:
{{
  "recommended_action": "ONE_OF_THE_FOUR_ACTIONS",
  "reason": "concise rationale, at most 3 sentences",
  "evidence_ids": ["only ids listed in the verified facts"],
  "event_ids": ["only ids listed in the verified facts"],
  "simulation_id": "a simulation id from the verified facts or null",
  "alternatives": [{{"action": "ACTION", "reason": "one line"}}],
  "llm_confidence": 0.0
}}

Verified facts (transaction {transaction_id}):
{context_json}
"""


class HttpDecisionLLMProvider(DecisionLLMProvider):
    """Minimal OpenAI-compatible chat-completions provider (stdlib only).

    Configured through environment variables (see backend/.env.example):

        DECISION_LLM_PROVIDER=openai_compatible
        DECISION_LLM_BASE_URL=https://api.example.com/v1
        DECISION_LLM_API_KEY=...
        DECISION_LLM_MODEL=...
        DECISION_LLM_TIMEOUT_MS=30000

    Any failure raises LLMProviderError so the caller falls back.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "openai_compatible_http"

    def generate(self, context: DecisionContext) -> DecisionProposal:
        payload = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You return strict JSON only. Never add markdown, "
                            "never add commentary outside the JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": _JSON_PROMPT.format(
                            transaction_id=context.transaction_id,
                            context_json=_context_json(context),
                        ),
                    },
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise LLMProviderError(f"provider network error: {exc}") from exc
        except TimeoutError as exc:
            raise LLMProviderError("provider request timed out") from exc

        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                f"provider returned an unparsable response: {exc}"
            ) from exc
        return parse_llm_json(content)


def _context_json(context: DecisionContext) -> str:
    """Deterministic JSON rendering of the verified context (no raw events)."""
    return json.dumps(
        {
            "transaction_id": context.transaction_id,
            "outcome": context.outcome,
            "outcome_confidence": context.outcome_confidence,
            "primary_reason": {
                "code": context.primary_reason_code,
                "message": context.primary_reason_message,
            },
            "consistency_status": context.consistency_status,
            "evidence": [
                {
                    "evidence_id": item[0],
                    "category": item[1],
                    "claim": item[2],
                    "strength": item[3],
                    "confidence": item[4],
                }
                for item in context.evidence_claims
            ],
            "evidence_gaps": [
                {"event_type": gap[0], "note": gap[1]}
                for gap in context.evidence_gaps
            ],
            "contradictions": [
                {"type": c[0], "rule_id": c[1], "explanation": c[2]}
                for c in context.contradictions
            ],
            "compound_failure": {
                "detected": context.compound_failure_detected,
                "severity": context.compound_failure_severity,
                "failure_chain": [
                    {"kind": node[0], "stage": node[1], "label": node[2]}
                    for node in context.failure_chain
                ],
                "root_causes": list(context.root_cause_kinds),
            },
            "impact": {
                "impact_score": context.impact_score,
                "scope": context.impact_scope,
                "affected_transactions": context.affected_transactions,
            },
            "simulations": [
                {
                    "intervention_type": fact.intervention_type,
                    "status": fact.status,
                    "simulation_id": fact.simulation_id,
                    "simulated_outcome": fact.simulated_outcome,
                    "delta_impact_score": fact.delta_impact_score,
                    "resolved_failure_kinds": list(fact.resolved_failure_kinds),
                    "remaining_failure_kinds": list(fact.remaining_failure_kinds),
                }
                for fact in context.simulations
            ],
            "comparison": [
                {"intervention_type": item[0], "rank": item[1]}
                for item in context.comparison
            ],
            "payment_captured": context.payment_captured,
            "refund_recorded": context.refund_recorded,
            "customer_impacting": context.customer_impacting,
            "evidence_confidence": context.evidence_confidence,
            "allowed_actions": list(ALL_ACTIONS),
            "allowed_simulation_ids": sorted(context.simulation_ids),
            "allowed_evidence_ids": sorted(context.all_evidence_ids),
            "allowed_event_ids": sorted(context.all_event_ids),
        },
        sort_keys=True,
    )


def parse_llm_json(content: str) -> DecisionProposal:
    """Parse the model's strict-JSON content into a DecisionProposal.

    Raises LLMProviderError on malformed content. Semantic validation
    (registered action, real ids, bounded confidence) happens separately in
    validate_proposal().
    """
    text = content.strip()
    if text.startswith("```"):
        # Tolerate a single markdown code fence around the JSON.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LLMProviderError(f"malformed JSON from provider: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("provider JSON is not an object")

    action = data.get("recommended_action")
    if not isinstance(action, str):
        raise LLMProviderError("missing recommended_action")
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise LLMProviderError("reason is not a string")

    evidence_ids = _string_list(data.get("evidence_ids") or [], "evidence_ids")
    event_ids = _string_list(data.get("event_ids") or [], "event_ids")
    simulation_id = data.get("simulation_id")
    if simulation_id is not None and not isinstance(simulation_id, str):
        raise LLMProviderError("simulation_id is not a string")

    alternatives = []
    raw_alternatives = data.get("alternatives") or []
    if not isinstance(raw_alternatives, list):
        raise LLMProviderError("alternatives is not a list")
    for item in raw_alternatives:
        if not isinstance(item, dict):
            raise LLMProviderError("alternative is not an object")
        alt_action = item.get("action")
        alt_reason = item.get("reason", "")
        if not isinstance(alt_action, str) or not isinstance(alt_reason, str):
            raise LLMProviderError("alternative action/reason must be strings")
        alternatives.append(AlternativeAction(action=alt_action, reason=alt_reason))

    confidence = data.get("llm_confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            raise LLMProviderError("llm_confidence is not numeric") from None

    return DecisionProposal(
        recommended_action=action,
        reason=reason,
        evidence_ids=tuple(evidence_ids),
        event_ids=tuple(event_ids),
        simulation_id=simulation_id,
        alternatives=tuple(alternatives),
        llm_confidence=confidence,
    )


def _string_list(value, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise LLMProviderError(f"{field_name} is not a list")
    if not all(isinstance(item, str) for item in value):
        raise LLMProviderError(f"{field_name} contains non-string values")
    return value


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

DISABLED_PROVIDER_VALUES = {"", "none", "disabled", "off", "0"}


def build_provider(settings: Optional[Settings] = None) -> Optional[DecisionLLMProvider]:
    """Build the configured provider from the environment.

    Returns None when no provider is configured — the caller then uses the
    deterministic fallback automatically. Never raises for a missing key.
    """
    settings = settings or get_settings()
    provider_name = getattr(settings, "decision_llm_provider", "none") or "none"
    if provider_name.lower() in DISABLED_PROVIDER_VALUES:
        return None
    if provider_name.lower() == "openai_compatible":
        base_url = getattr(settings, "decision_llm_base_url", "") or ""
        api_key = getattr(settings, "decision_llm_api_key", "") or ""
        model = getattr(settings, "decision_llm_model", "") or ""
        timeout_ms = int(getattr(settings, "decision_llm_timeout_ms", 30000) or 30000)
        if not base_url or not model:
            return None
        return HttpDecisionLLMProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=max(1.0, timeout_ms / 1000.0),
        )
    return None