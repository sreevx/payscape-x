"""Future: orchestrate agents across the journey."""

from app.agents.base import BaseAgent


class AgentOrchestrator(BaseAgent):
    """(Placeholder) Runs the agent pipeline in the correct order per journey."""

    name = "orchestrator"