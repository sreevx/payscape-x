"""Primitives for the future Evidence Engine."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EvidenceItem:
    """A validated event attached to a journey as evidence.

    No evidence collection is implemented in Part 1.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str = ""
    event_type: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = field(default_factory=dict)
    valid: bool = True


class EvidenceEngine:
    """(Placeholder) Collects and validates structured events."""

    def collect(self, transaction_id: str) -> list[EvidenceItem]:
        raise NotImplementedError(
            "EvidenceEngine is a placeholder. Evidence arrives in Part 3."
        )