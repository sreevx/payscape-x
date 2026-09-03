"""Read API contract for the Consistency Engine (Part 4).

The response contains deterministic rule results only: PASS / VIOLATION /
INSUFFICIENT_EVIDENCE / NOT_APPLICABLE per rule, plus the aggregated
overall_integrity. overall_integrity reflects record agreement — it is NOT
a business outcome and must never be rendered as SUCCESS / FAILED /
AT_RISK / FULFILLED.
"""

from pydantic import BaseModel, ConfigDict


class ConsistencyCheck(BaseModel):
    """One evaluated consistency rule."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    name: str
    description: str
    severity: str  # LOW | MEDIUM | HIGH
    # PASS | VIOLATION | INSUFFICIENT_EVIDENCE | NOT_APPLICABLE
    status: str
    supporting_event_ids: list[str]
    explanation: str


class ConsistencyResult(BaseModel):
    """The full consistency report for one transaction."""

    transaction_id: str
    checks: list[ConsistencyCheck]
    passed: list[str]
    violations: list[str]
    insufficient_evidence: list[str]
    not_applicable: list[str]
    # CONSISTENT | INCONSISTENT | INSUFFICIENT_EVIDENCE
    overall_integrity: str