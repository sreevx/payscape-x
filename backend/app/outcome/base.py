"""Outcome classification vocabulary.

The four business-outcome states are a domain contract shared across the
system. The deterministic engine that *computes* them lives in the rest of
this package (rules.py + engine.py) — Part 5.
"""

from enum import Enum


class OutcomeState(str, Enum):
    """Business outcome of a transaction."""

    FULFILLED = "FULFILLED"
    AT_RISK = "AT_RISK"
    FAILED = "FAILED"
    UNVERIFIABLE = "UNVERIFIABLE"