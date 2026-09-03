"""Base interface for every PAYSCAPE-X agent.

Agents are NOT implemented in Part 1 (Rule 1). Subclasses define their
`name` and document their future responsibility; `run` is stubbed to fail
loudly so nothing accidentally pretends to be intelligent.
"""

from typing import Any


class BaseAgent:
    """Interface every agent must implement in later parts."""

    name: str = "base_agent"

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent against a journey context.

        Raises:
            NotImplementedError: always — agents arrive in Part 3.
        """
        raise NotImplementedError(
            f"Agent '{self.name}' is a placeholder. AI agents arrive in Part 3."
        )