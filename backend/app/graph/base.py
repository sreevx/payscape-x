"""Primitives for the future journey graph.

Pure data structures — no graph algorithms are implemented in Part 1.
"""

import uuid
from dataclasses import dataclass, field


@dataclass
class JourneyNode:
    """A stage or event in a transaction journey."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: str = "unknown"
    event_type: str | None = None


@dataclass
class JourneyEdge:
    """A transition between two journey stages."""

    source: str
    target: str
    label: str = ""


@dataclass
class JourneyGraph:
    """Placeholder container for a reconstructed journey.

    Journey Reconstruction is implemented in Part 3.
    """

    transaction_id: str
    nodes: list[JourneyNode] = field(default_factory=list)
    edges: list[JourneyEdge] = field(default_factory=list)