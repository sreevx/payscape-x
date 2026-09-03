"""Base interface for declarative rules."""

from typing import Any


class BaseRule:
    """Interface for business rules evaluated against a journey context.

    Not implemented in Part 1 — rules arrive with the Consistency and
    Outcome engines.
    """

    rule_id: str = "base_rule"

    def evaluate(self, context: dict[str, Any]) -> list[str]:
        """Return findings for the given context.

        Raises:
            NotImplementedError: always — rules arrive in later parts.
        """
        raise NotImplementedError(
            f"Rule '{self.rule_id}' is a placeholder."
        )