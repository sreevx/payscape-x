"""Canonical internal event representation (Part 3).

`CanonicalEvent` is the deterministic, provider-agnostic internal shape that
the ingestion pipeline produces. It is deliberately NOT a database model —
`TransactionEvent` remains the persisted unified stream. Adapters translate
raw provider payloads into a `CanonicalEvent`, the normalizer maps event
types/sources into the centralized Part 2 registry, and the validator checks
structure.

An event that survives the pipeline but has no deterministic correlation
identity is preserved as an ORPHAN; an event whose type/source is not in the
registry is preserved and marked UNKNOWN. Neither is ever silently dropped.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class IngestionStatus(str, Enum):
    """Lifecycle of one canonical event through the ingestion pipeline."""

    PENDING = "PENDING"          # adapter produced it
    VALIDATED = "VALIDATED"      # structural checks passed
    NORMALIZED = "NORMALIZED"    # event type/source mapped to the registry
    CORRELATED = "CORRELATED"    # deterministic correlation resolved
    UNKNOWN = "UNKNOWN"          # type/source not in registry — preserved, not classified
    ORPHAN = "ORPHAN"            # no deterministic correlation identity — preserved, not persisted
    DUPLICATE = "DUPLICATE"      # same idempotency identity already ingested
    PERSISTED = "PERSISTED"      # written to the unified TransactionEvent stream
    REJECTED = "REJECTED"        # structurally malformed — rejected with errors


@dataclass
class CanonicalEvent:
    """Provider-agnostic event, ready for normalization and correlation.

    `original_event_reference` points at the raw source (e.g. the
    TransactionEvent row a synthetic event came from, or a future webhook
    record) so nothing is ever disconnected from its origin.
    """

    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    order_id: Optional[uuid.UUID] = None
    payment_id: Optional[uuid.UUID] = None
    correlation_id: Optional[uuid.UUID] = None
    idempotency_key: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    ingestion_status: IngestionStatus = IngestionStatus.PENDING
    original_event_reference: dict[str, Any] = field(default_factory=dict)
    is_unknown: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestionResult:
    """Outcome of ingesting one raw event. Never ambiguous, never silent."""

    event: CanonicalEvent
    status: IngestionStatus
    message: str
    errors: list[str] = field(default_factory=list)
    persisted_event_id: Optional[str] = None
    duplicate_of_event_id: Optional[str] = None
    correlation_reason: Optional[str] = None