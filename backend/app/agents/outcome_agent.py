"""Future: classify business outcomes."""

from app.agents.base import BaseAgent


class OutcomeAgent(BaseAgent):
    """(Placeholder) Classifies outcomes as FULFILLED / AT_RISK / FAILED / UNVERIFIABLE."""

    name = "outcome_agent"