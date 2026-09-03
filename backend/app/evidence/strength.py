"""Deterministic evidence-strength resolution (Part 4).

A claim's strength is decided purely by what the records contain:

- events exist and agree with an independent record  -> CORROBORATED
- events exist, no independent record to compare     -> DIRECT
- events exist but conflict with other recorded events -> CONTRADICTED
- events absent but structurally expected             -> MISSING
- events absent and not structurally expected         -> (not reported)

The decision table is explicit and deterministic: given the same inputs it
always returns the same strength. No probability, no heuristics, no AI.
"""

from typing import Optional

from app.evidence.models import (
    STRENGTH_CONTRADICTED,
    STRENGTH_CORROBORATED,
    STRENGTH_DIRECT,
    STRENGTH_MISSING,
    STRENGTH_CONFIDENCE,
)


def resolve_strength(
    *,
    present: bool,
    corroborated: bool,
    contradicted: bool,
    structurally_expected: bool,
) -> Optional[str]:
    """Return the evidence strength for one claim, or None when the claim
    should not be reported at all (absent and not structurally expected)."""
    if contradicted:
        return STRENGTH_CONTRADICTED
    if present and corroborated:
        return STRENGTH_CORROBORATED
    if present:
        return STRENGTH_DIRECT
    if structurally_expected:
        return STRENGTH_MISSING
    return None


def confidence_for(strength: str) -> float:
    """Deterministic confidence for a strength level."""
    return STRENGTH_CONFIDENCE[strength]