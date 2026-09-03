"""Journey integrity detection (Part 3).

Structural observations over a reconstructed journey. Every finding is a
description of what the raw stream contains — nothing here classifies the
transaction's business outcome and nothing here decides what SHOULD have
happened.

Detections (all deterministic):

- duplicates: same idempotency key appearing more than once; webhook rows
  delivered twice with the same provider event id
- missing-event candidates: structural rules of the form "if X is present
  and Y is absent, Y is a candidate" — a structural observation only
- contradictions: mutually exclusive states both present (capture + failure,
  delivered + failed, refund completed without initiation) — recorded, not
  resolved, neither event deleted
- out-of-order: timestamp order != ingestion order (no timestamps mutated)
- delayed: WEBHOOK_DELAYED events and webhook rows flagged DELAYED
- unknown: event types/sources outside the centralized registry
- orphan: events whose correlation does not match the journey's own
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import WebhookProcessingStatus
from app.core.events import ALL_EVENT_TYPES, EventType
from app.journey.reconstructor import JourneyEvent, ReconstructedJourney
from app.models import Webhook


@dataclass(frozen=True)
class MissingEventRule:
    """Structural rule: when every `requires` type is present and none of
    `expects` is present, each missing `expects` type is a candidate."""

    rule_id: str
    requires: frozenset[str]
    expects: frozenset[str]


# Structural expectations — purely "X present but Y absent" observations.
MISSING_EVENT_RULES: list[MissingEventRule] = [
    MissingEventRule(
        "MISSING_WEBHOOK_AFTER_CAPTURE",
        frozenset({EventType.PAYMENT_CAPTURED.value}),
        frozenset({EventType.WEBHOOK_RECEIVED.value}),
    ),
    MissingEventRule(
        "MISSING_CONFIRMATION_AFTER_CAPTURE",
        frozenset({EventType.PAYMENT_CAPTURED.value}),
        frozenset({EventType.ORDER_CONFIRMED.value}),
    ),
    MissingEventRule(
        "MISSING_ALLOCATION_AFTER_CONFIRMATION",
        frozenset({EventType.ORDER_CONFIRMED.value}),
        frozenset(
            {
                EventType.INVENTORY_RESERVED.value,
                EventType.INVENTORY_OUT_OF_STOCK.value,
            }
        ),
    ),
    MissingEventRule(
        "MISSING_FULFILLMENT_AFTER_RESERVATION",
        frozenset({EventType.INVENTORY_RESERVED.value}),
        frozenset({EventType.FULFILLMENT_CREATED.value}),
    ),
    MissingEventRule(
        "MISSING_SHIPMENT_AFTER_FULFILLMENT",
        frozenset({EventType.FULFILLMENT_SHIPPED.value}),
        frozenset({EventType.SHIPMENT_CREATED.value}),
    ),
    MissingEventRule(
        "MISSING_DELIVERY_RESOLUTION",
        frozenset({EventType.SHIPMENT_CREATED.value}),
        frozenset(
            {
                EventType.SHIPMENT_IN_TRANSIT.value,
                EventType.DELIVERY_COMPLETED.value,
                EventType.DELIVERY_FAILED.value,
                EventType.DELIVERY_RETURNED.value,
            }
        ),
    ),
]

# Contradiction rules: either two mutually exclusive types are both present,
# or a completion exists without its required initiation.
CONTRADICTION_RULES: list[dict] = [
    {
        "type": "PAYMENT_STATE_CONTRADICTION",
        "rule_id": "PAYMENT_CAPTURED_AND_FAILED",
        "explanation": (
            "both PAYMENT_CAPTURED and PAYMENT_FAILED are recorded for the "
            "same payment; both are preserved, neither is preferred"
        ),
        "requires": frozenset(
            {EventType.PAYMENT_CAPTURED.value, EventType.PAYMENT_FAILED.value}
        ),
    },
    {
        "type": "DELIVERY_STATE_CONTRADICTION",
        "rule_id": "DELIVERED_AND_DELIVERY_FAILED",
        "explanation": (
            "both DELIVERY_COMPLETED and DELIVERY_FAILED are recorded for the "
            "same journey; both are preserved, neither is preferred"
        ),
        "requires": frozenset(
            {
                EventType.DELIVERY_COMPLETED.value,
                EventType.DELIVERY_FAILED.value,
            }
        ),
    },
    {
        "type": "REFUND_WITHOUT_INITIATION",
        "rule_id": "REFUND_COMPLETED_WITHOUT_INITIATED",
        "explanation": (
            "REFUND_COMPLETED is recorded but no REFUND_INITIATED exists; "
            "the completion is preserved and flagged structurally"
        ),
        "requires": frozenset({EventType.REFUND_COMPLETED.value}),
        "absent": frozenset({EventType.REFUND_INITIATED.value}),
    },
]

UNKNOWN_EVENT_REASON = "event type/source is not in the centralized registry"
ORPHAN_EVENT_REASON = (
    "event correlation does not match the journey's correlation; preserved "
    "as recorded, not merged"
)


@dataclass
class MissingCandidate:
    event_type: str
    rule_id: str
    note: str


@dataclass
class Contradiction:
    type: str
    rule_id: str
    involved_event_ids: list[str] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    explanation: str = ""


@dataclass
class Duplicate:
    event_id: str
    event_type: str
    idempotency_key: str
    canonical_event_id: str
    rule_id: str


@dataclass
class OutOfOrder:
    event_id: str
    event_type: str
    timestamp: datetime
    ingestion_position: int
    chronological_position: int


@dataclass
class Delayed:
    event_id: str
    event_type: str
    delay_minutes: Optional[float]


@dataclass
class UnknownEvent:
    event_id: str
    event_type: str
    reason: str


@dataclass
class OrphanEvent:
    event_id: str
    event_type: str
    correlation_id: str
    reason: str


@dataclass
class JourneyIntegrity:
    """Structural integrity report for one reconstructed journey."""

    transaction_id: str
    total_events: int
    linked_events: int
    first_event_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    missing_expected_event_candidates: list[MissingCandidate] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    out_of_order_events: list[OutOfOrder] = field(default_factory=list)
    delayed_events: list[Delayed] = field(default_factory=list)
    unknown_events: list[UnknownEvent] = field(default_factory=list)
    orphan_events: list[OrphanEvent] = field(default_factory=list)

    @property
    def orphan_count(self) -> int:
        return len(self.orphan_events)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def unknown_count(self) -> int:
        return len(self.unknown_events)

    @property
    def delayed_count(self) -> int:
        return len(self.delayed_events)

    @property
    def out_of_order_count(self) -> int:
        return len(self.out_of_order_events)


def analyze(
    journey: ReconstructedJourney, webhooks: Optional[list[Webhook]] = None
) -> JourneyIntegrity:
    """Compute the integrity report and flag the journey's events."""
    events = journey.chronological_events
    integrity = JourneyIntegrity(
        transaction_id=journey.transaction_id,
        total_events=journey.total_events,
        linked_events=journey.total_events,
        first_event_at=journey.first_event_at,
        last_event_at=journey.last_event_at,
        duration_seconds=journey.duration_seconds,
    )

    _detect_unknowns(events, integrity)
    _detect_orphans(events, journey, integrity)
    _detect_duplicates(events, webhooks or [], integrity)
    _detect_out_of_order(events, integrity)
    _detect_delayed(events, webhooks or [], integrity)
    _detect_missing_candidates(events, integrity)
    _detect_contradictions(events, integrity)

    integrity.linked_events = (
        journey.total_events - integrity.orphan_count - integrity.unknown_count
    )
    return integrity


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_unknowns(events: list[JourneyEvent], integrity: JourneyIntegrity) -> None:
    for event in events:
        if event.event_type not in ALL_EVENT_TYPES:
            event.is_unknown = True
            integrity.unknown_events.append(
                UnknownEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    reason=UNKNOWN_EVENT_REASON,
                )
            )


def _detect_orphans(
    events: list[JourneyEvent],
    journey: ReconstructedJourney,
    integrity: JourneyIntegrity,
) -> None:
    for event in events:
        if journey.correlation_id is None:
            continue
        if event.correlation_id != journey.correlation_id:
            event.is_orphan = True
            integrity.orphan_events.append(
                OrphanEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    correlation_id=event.correlation_id,
                    reason=ORPHAN_EVENT_REASON,
                )
            )


def _detect_duplicates(
    events: list[JourneyEvent],
    webhooks: list[Webhook],
    integrity: JourneyIntegrity,
) -> None:
    # Rule 1: unified events sharing an idempotency key (earliest is canonical).
    by_key: dict[str, list[JourneyEvent]] = {}
    for event in events:
        if event.idempotency_key:
            by_key.setdefault(event.idempotency_key, []).append(event)
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda event: (event.timestamp, event.event_id))
        canonical = ordered[0]
        for event in ordered[1:]:
            event.is_duplicate = True
            event.duplicate_of_event_id = canonical.event_id
            integrity.duplicates.append(
                Duplicate(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    idempotency_key=key,
                    canonical_event_id=canonical.event_id,
                    rule_id="DUPLICATE_IDEMPOTENCY_KEY",
                )
            )

    # Rule 2: webhook rows delivered twice with the same provider event id.
    by_provider_id: dict[str, list[Webhook]] = {}
    for webhook in webhooks:
        by_provider_id.setdefault(webhook.provider_event_id, []).append(webhook)
    for provider_id, group in by_provider_id.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda hook: hook.received_at)
        canonical = ordered[0]
        for hook in ordered[1:]:
            integrity.duplicates.append(
                Duplicate(
                    event_id=str(hook.id),
                    event_type=hook.event_type,
                    idempotency_key=provider_id,
                    canonical_event_id=str(canonical.id),
                    rule_id="DUPLICATE_WEBHOOK_ROW",
                )
            )


def _detect_out_of_order(
    events: list[JourneyEvent], integrity: JourneyIntegrity
) -> None:
    chronological = sorted(events, key=lambda event: (event.timestamp, event.event_id))
    chronological_position = {
        event.event_id: index for index, event in enumerate(chronological)
    }
    for event in chronological:
        if chronological_position[event.event_id] != event.ingestion_position:
            integrity.out_of_order_events.append(
                OutOfOrder(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    timestamp=event.timestamp,
                    ingestion_position=event.ingestion_position,
                    chronological_position=chronological_position[event.event_id],
                )
            )


def _detect_delayed(
    events: list[JourneyEvent],
    webhooks: list[Webhook],
    integrity: JourneyIntegrity,
) -> None:
    for event in events:
        if event.event_type == EventType.WEBHOOK_DELAYED.value:
            integrity.delayed_events.append(
                Delayed(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    delay_minutes=_delay_minutes(event.payload),
                )
            )
    for hook in webhooks:
        if hook.processing_status == WebhookProcessingStatus.DELAYED:
            integrity.delayed_events.append(
                Delayed(
                    event_id=str(hook.id),
                    event_type=hook.event_type,
                    delay_minutes=None,
                )
            )


def _delay_minutes(payload: dict) -> Optional[float]:
    raw = payload.get("delay_minutes")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _detect_missing_candidates(
    events: list[JourneyEvent], integrity: JourneyIntegrity
) -> None:
    present = {event.event_type for event in events}
    for rule in MISSING_EVENT_RULES:
        if not rule.requires.issubset(present):
            continue
        if rule.expects & present:
            continue
        for expected in sorted(rule.expects):
            integrity.missing_expected_event_candidates.append(
                MissingCandidate(
                    event_type=expected,
                    rule_id=rule.rule_id,
                    note=(
                        f"{', '.join(sorted(rule.requires))} present but "
                        f"{expected} absent"
                    ),
                )
            )


def _detect_contradictions(
    events: list[JourneyEvent], integrity: JourneyIntegrity
) -> None:
    by_type: dict[str, list[JourneyEvent]] = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event)

    for rule in CONTRADICTION_RULES:
        requires = rule["requires"]
        present_types = {event_type for event_type in requires if event_type in by_type}
        if rule.get("absent"):
            # Completion-without-initiation style rules: the completion type
            # is present and none of the required initiation types exist.
            if present_types and not (
                set(by_type.keys()) & rule["absent"]
            ):
                involved = [
                    event for event_type in present_types
                    for event in by_type[event_type]
                ]
                integrity.contradictions.append(
                    _contradiction_from_events(rule, involved)
                )
            continue
        if len(present_types) >= 2:
            involved = [
                event
                for event_type in sorted(by_type.keys())
                if event_type in requires
                for event in by_type[event_type]
            ]
            integrity.contradictions.append(_contradiction_from_events(rule, involved))


def _contradiction_from_events(rule: dict, events: list[JourneyEvent]) -> Contradiction:
    ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))
    return Contradiction(
        type=rule["type"],
        rule_id=rule["rule_id"],
        involved_event_ids=[event.event_id for event in ordered],
        timestamps=[event.timestamp for event in ordered],
        explanation=rule["explanation"],
    )