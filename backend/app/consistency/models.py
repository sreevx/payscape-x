"""Consistency Engine domain models (Part 4).

Deterministic structures produced by the rule evaluator. The engine answers
"do the observed records agree with each other?" — it never answers "did the
customer ultimately receive the promised business outcome?" (Part 5).

Rule statuses (spec §10):

- PASS                 — the rule's evidence exists and agrees
- VIOLATION            — the rule's evidence exists and disagrees
- INSUFFICIENT_EVIDENCE — the rule plausibly applies but key records are
                         absent; absence of evidence is NOT evidence of
                         failure
- NOT_APPLICABLE       — the rule does not apply to this journey

overall_integrity is NOT a business outcome; it only reflects record
agreement:
- INCONSISTENT          any rule VIOLATION
- CONSISTENT            no violations and at least one PASS
- INSUFFICIENT_EVIDENCE no violations and no PASS (nothing verifiable)
"""

from dataclasses import dataclass, field
from typing import Optional

STATUS_PASS = "PASS"
STATUS_VIOLATION = "VIOLATION"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

ALL_STATUSES = (
    STATUS_PASS,
    STATUS_VIOLATION,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NOT_APPLICABLE,
)

INTEGRITY_CONSISTENT = "CONSISTENT"
INTEGRITY_INCONSISTENT = "INCONSISTENT"
INTEGRITY_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"


@dataclass
class CheckOutcome:
    """The deterministic outcome of evaluating one rule."""

    rule_id: str
    status: str
    supporting_event_ids: list[str]
    explanation: str


@dataclass
class ConsistencyCheck:
    """One evaluated rule with its metadata."""

    rule_id: str
    name: str
    description: str
    severity: str
    status: str
    supporting_event_ids: list[str]
    explanation: str


@dataclass
class ConsistencyResult:
    """The full consistency report for one transaction."""

    transaction_id: str
    checks: list[ConsistencyCheck] = field(default_factory=list)

    @property
    def passed(self) -> list[str]:
        return [check.rule_id for check in self.checks if check.status == STATUS_PASS]

    @property
    def violations(self) -> list[str]:
        return [
            check.rule_id for check in self.checks if check.status == STATUS_VIOLATION
        ]

    @property
    def insufficient_evidence(self) -> list[str]:
        return [
            check.rule_id
            for check in self.checks
            if check.status == STATUS_INSUFFICIENT_EVIDENCE
        ]

    @property
    def not_applicable(self) -> list[str]:
        return [
            check.rule_id
            for check in self.checks
            if check.status == STATUS_NOT_APPLICABLE
        ]

    @property
    def overall_integrity(self) -> str:
        if self.violations:
            return INTEGRITY_INCONSISTENT
        if self.passed:
            return INTEGRITY_CONSISTENT
        return INTEGRITY_INSUFFICIENT_EVIDENCE