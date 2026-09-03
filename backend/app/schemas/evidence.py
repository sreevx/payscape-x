"""Read API contract for the Evidence Engine (Part 4).

The evidence response contains deterministic data only: structured evidence
items with their supporting event ids, evidence gaps (structural
observations) and contradictions (preserved, not resolved). No outcome
classification, no AI reasoning.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EvidenceItem(BaseModel):
    """One evidence item: a deterministic claim backed by concrete records."""

    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    category: str
    claim: str
    event_ids: list[str]
    source: str
    timestamp: Optional[datetime] = None
    supporting_data: dict
    # DIRECT | CORROBORATED | INDIRECT | MISSING | CONTRADICTED
    strength: str
    rule_id: str
    confidence: float
    contradictions: list[str] = []
    metadata: dict = {}


class EvidenceGapItem(BaseModel):
    """A structurally expected event type that was not observed."""

    event_type: str
    rule_id: str
    note: str


class EvidenceContradictionItem(BaseModel):
    """Two mutually exclusive states both recorded (preserved, not resolved)."""

    contradiction_id: str
    type: str
    rule_id: str
    event_ids: list[str]
    explanation: str
    severity: str  # LOW | MEDIUM | HIGH


class EvidenceReport(BaseModel):
    """The complete evidence report for one transaction journey."""

    transaction_id: str
    evidence: list[EvidenceItem]
    gaps: list[EvidenceGapItem]
    contradictions: list[EvidenceContradictionItem]
    strength_summary: dict[str, int]