"""AI Decision Agent (Part 8).

REASON -> RECOMMEND -> WAIT FOR HUMAN.

The agent reasons ONLY over the verified facts produced by Parts 1-7 and
recommends exactly one action from the closed registry (DO_NOTHING,
RECOVER_ROOT_CAUSE, REFUND_OR_CONTAIN, HUMAN_REVIEW). Approval records
merchant approval; nothing here ever executes a refund, payment, message
or any external action. Without any LLM provider the deterministic fallback
produces the same structured recommendation.
"""

from app.decision.models import (
    ACTION_DO_NOTHING,
    ACTION_HUMAN_REVIEW,
    ACTION_RECOVER_ROOT_CAUSE,
    ACTION_REFUND_OR_CONTAIN,
    ALL_ACTIONS,
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    DecisionContext,
    DecisionProposal,
    DecisionResult,
    SimulationFact,
)
from app.decision.rules import FALLBACK_RULES, fallback_decision

__all__ = [
    "ACTION_DO_NOTHING",
    "ACTION_HUMAN_REVIEW",
    "ACTION_RECOVER_ROOT_CAUSE",
    "ACTION_REFUND_OR_CONTAIN",
    "ALL_ACTIONS",
    "APPROVAL_APPROVED",
    "APPROVAL_PENDING",
    "APPROVAL_REJECTED",
    "DecisionContext",
    "DecisionProposal",
    "DecisionResult",
    "FALLBACK_RULES",
    "SimulationFact",
    "fallback_decision",
]