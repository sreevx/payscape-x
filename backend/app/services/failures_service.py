"""Compound Failure Engine service (Part 6).

Composition layer between the API routes and the deterministic
`app.failures` modules. It loads the same pipeline the analysis package
uses (journey -> evidence -> consistency -> outcome) and then runs the
compound-failure analysis on top of it:

    journey      -> reconstruct (Part 3)
    evidence     -> collect (Part 4)
    consistency  -> evaluate (Part 4)
    outcome      -> decide (Part 5)
    failure      -> analyze (Part 6)

Returns None for unknown transaction ids (the routes turn that into 404).
The dataset list endpoint pre-filters candidates by the event markers the
outcome engine uses, so journeys that can never be FAILED are skipped —
the filter list mirrors `app/outcome/rules.py` and is asserted by tests.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.events import EventType
from app.failures.engine import analyze
from app.failures.models import CompoundFailureResult
from app.models import Order, ScenarioInstance, TransactionEvent
from app.schemas.failures import (
    ChainEdgeItem,
    CompoundFailureResponse,
    FailureListItem,
    FailureListResponse,
    FailureNodeItem,
    RootCauseItem,
)
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.outcome_service import build_outcome

# Event markers that can produce a FAILED business outcome (mirrors the
# Part 5 rule registry — journeys without any of these are skipped by the
# dataset scan).
FAILURE_MARKER_EVENT_TYPES = [
    EventType.PAYMENT_FAILED.value,
    EventType.ORDER_CANCELLED.value,
    EventType.ORDER_NOT_CONFIRMED.value,
    EventType.INVENTORY_OUT_OF_STOCK.value,
    EventType.NO_FULFILLMENT.value,
    EventType.FULFILLMENT_FAILED.value,
    EventType.DELIVERY_FAILED.value,
    EventType.DELIVERY_RETURNED.value,
]


def build_failure(journey, integrity, evidence, consistency, outcome) -> CompoundFailureResult:
    """Pure: run the deterministic compound-failure engine."""
    return analyze(journey, integrity, evidence, consistency, outcome)


def _node_item(node) -> FailureNodeItem:
    return FailureNodeItem(
        node_id=node.node_id,
        kind=node.kind,
        stage=node.stage,
        label=node.label,
        status=node.status,
        message=node.message,
        rule_id=node.rule_id,
        event_ids=node.event_ids,
        evidence_ids=node.evidence_ids,
        timestamp=node.timestamp,
        metadata=dict(node.metadata),
    )


def _failure_schema(result: CompoundFailureResult) -> CompoundFailureResponse:
    return CompoundFailureResponse(
        compound_failure_id=result.compound_failure_id,
        transaction_id=result.transaction_id,
        detected=result.detected,
        reason=result.reason,
        severity=result.severity,
        classification=result.classification,
        primary_failure=(
            _node_item(result.primary_failure)
            if result.primary_failure is not None
            else None
        ),
        failure_chain=[_node_item(node) for node in result.failure_chain],
        edges=[
            ChainEdgeItem(
                edge_id=edge.edge_id,
                source_node=edge.source_node,
                target_node=edge.target_node,
                relationship_type=edge.relationship_type,
                rule_id=edge.rule_id,
                reason=edge.reason,
            )
            for edge in result.edges
        ],
        root_causes=[
            RootCauseItem(
                root_cause_id=root.root_cause_id,
                kind=root.kind,
                label=root.label,
                stage=root.stage,
                explanation=root.explanation,
                rule_id=root.rule_id,
                event_ids=root.event_ids,
                evidence_ids=root.evidence_ids,
            )
            for root in result.root_causes
        ],
        confidence=result.confidence,
        event_ids=result.event_ids,
        evidence_ids=result.evidence_ids,
        metadata=dict(result.metadata),
    )


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None


def get_failure(session: Session, transaction_id: str) -> Optional[CompoundFailureResponse]:
    """Load + analyze + map. None when the transaction is unknown."""
    payment_uuid = _resolve_transaction_id(transaction_id)
    if payment_uuid is None:
        return None
    result = journeys_service._reconstruct_all(session, transaction_id)
    if result is None:
        return None
    journey, integrity, _graph = result
    context = load_domain_context(session, payment_uuid)
    if context is None:
        return None
    evidence = build_evidence(journey, integrity, context)
    consistency = build_consistency(journey, context)
    outcome = build_outcome(journey, integrity, evidence, consistency)
    return _failure_schema(build_failure(journey, integrity, evidence, consistency, outcome))


# ---------------------------------------------------------------------------
# Dataset list scan
# ---------------------------------------------------------------------------

def _load_instances(session: Session) -> dict[str, ScenarioInstance]:
    rows = list(session.scalars(select(ScenarioInstance)))
    return {
        str(instance.metadata_.get("payment_id", "")): instance
        for instance in rows
        if instance.metadata_.get("payment_id")
    }


def _other_payments_on_shortage_skus(
    session: Session, payment_uuid: uuid.UUID, skus: list[str]
) -> tuple[set[str], dict[str, list[str]]]:
    """Other payments whose OUT_OF_STOCK records share the same SKUs.

    Cheap deterministic scan over OUT_OF_STOCK rows only — used by both the
    list endpoint (scope) and the impact service (cohort membership).
    Returns (other payment ids, payment -> skus seen).
    """
    if not skus:
        return set(), {}
    wanted = set(skus)
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value
            )
        )
    )
    other_payments: set[str] = set()
    skus_by_payment: dict[str, list[str]] = {}
    for row in rows:
        if row.payment_id is None or str(row.payment_id) == str(payment_uuid):
            continue
        payload_sku = (row.payload or {}).get("product_sku")
        if not payload_sku or payload_sku not in wanted:
            continue
        other_payments.add(str(row.payment_id))
        seen = set(skus_by_payment.setdefault(str(row.payment_id), []))
        seen.add(str(payload_sku))
        skus_by_payment[str(row.payment_id)] = sorted(seen)
    return other_payments, skus_by_payment


def _shortage_skus_for(session: Session, payment_uuid: uuid.UUID) -> list[str]:
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value,
                TransactionEvent.payment_id == payment_uuid,
            )
        )
    )
    skus = {
        str(row.payload.get("product_sku"))
        for row in rows
        if row.payload.get("product_sku")
    }
    return sorted(skus)


def _list_scope(
    session: Session, payment_uuid: uuid.UUID
) -> tuple[str, int, list[str]]:
    """Cheap scope: MULTI_TRANSACTION when other payments share the shortage
    SKUs. Returns (scope, affected_total, shared_skus)."""
    skus = _shortage_skus_for(session, payment_uuid)
    if not skus:
        return "SINGLE_TRANSACTION", 1, []
    others, _ = _other_payments_on_shortage_skus(session, payment_uuid, skus)
    if others:
        return "MULTI_TRANSACTION", len(others) + 1, skus
    return "SINGLE_TRANSACTION", 1, skus


# The deterministic dataset scan re-runs the Part 3-6 pipeline per
# candidate transaction. On PostgreSQL that pipeline is IO-bound (many
# round-trips to the database), so the scan runs across a small thread
# pool — every worker uses its own session/connection — and its output,
# which is a pure function of the seeded records, is memoized for a short
# TTL so repeat page loads are instant. Non-PostgreSQL engines (the
# in-memory SQLite test suite) keep the sequential single-session path.
_LIST_SCAN_THREADS = 5
_LIST_CACHE_TTL_SECONDS = 300
_list_cache_lock = threading.Lock()
_list_cache: dict = {}


def _marker_ordered_instances(session: Session) -> list[ScenarioInstance]:
    """Candidate instances carrying any FAILED-capable event marker."""
    instances = _load_instances(session)
    marker_payments = {
        str(payment_id)
        for payment_id in session.scalars(
            select(TransactionEvent.payment_id)
            .where(TransactionEvent.event_type.in_(FAILURE_MARKER_EVENT_TYPES))
            .distinct()
        )
    }

    def instance_key(instance: ScenarioInstance):
        return int(instance.metadata_.get("journey_index", 0))

    return sorted(
        (
            instance
            for instance in instances.values()
            if str(instance.metadata_.get("payment_id", "")) in marker_payments
        ),
        key=instance_key,
    )


def _analyze_instance(
    session: Session, instance: ScenarioInstance
) -> Optional[FailureListItem]:
    """Deep-analyze one candidate. Returns None when it is not a detected
    compound failure (outcome not FAILED, or no multi-stage chain)."""
    transaction_id = str(instance.metadata_["payment_id"])
    try:
        payment_uuid = uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None
    journey, integrity, _graph = journeys_service._reconstruct_all(
        session, transaction_id
    )
    if journey is None:
        return None
    context = load_domain_context(session, payment_uuid)
    if context is None:
        return None
    evidence = build_evidence(journey, integrity, context)
    consistency = build_consistency(journey, context)
    outcome = build_outcome(journey, integrity, evidence, consistency)
    if outcome.outcome != "FAILED":
        return None
    failure = build_failure(journey, integrity, evidence, consistency, outcome)
    if not failure.detected:
        return None

    primary = failure.primary_failure
    primary_kind = primary.kind if primary is not None else None
    primary_label = primary.label if primary is not None else None
    scope_value, affected_total, shared_skus = _list_scope(session, payment_uuid)

    order = None
    if journey.order_id:
        try:
            order = session.get(Order, uuid.UUID(journey.order_id))
        except (ValueError, AttributeError):
            order = None
    return FailureListItem(
        transaction_id=transaction_id,
        order_id=journey.order_id or "",
        external_order_id=order.external_order_id if order else "",
        scenario_type=instance.scenario_type.value,
        scenario_slug=str(instance.scenario_type.value).lower(),
        outcome=outcome.outcome,
        severity=failure.severity,
        classification=failure.classification,
        detected=True,
        primary_failure_kind=primary_kind,
        primary_failure_label=primary_label,
        root_cause_kinds=[root.kind for root in failure.root_causes],
        chain_length=len(failure.failure_chain),
        distinct_stages=sorted(
            {node.stage for node in failure.failure_chain}
        ),
        confidence=failure.confidence,
        scope=scope_value,
        affected_transactions=affected_total,
        shared_skus=shared_skus if scope_value == "MULTI_TRANSACTION" else [],
    )


def _scan_sequential(
    session: Session, ordered_instances: list[ScenarioInstance]
) -> list[FailureListItem]:
    """Single-session scan (non-PostgreSQL engines, tests)."""
    items: list[FailureListItem] = []
    for instance in ordered_instances:
        item = _analyze_instance(session, instance)
        if item is not None:
            items.append(item)
    return items


def _scan_parallel(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[FailureListItem]:
    """Threaded scan with one session/connection per worker. Deterministic:
    results are reassembled in the input order and each item is a pure
    function of its records, so the output equals the sequential scan."""
    factory = sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)
    workers = max(1, min(_LIST_SCAN_THREADS, len(ordered_instances)))

    def work(instance: ScenarioInstance) -> Optional[FailureListItem]:
        session = factory()
        try:
            return _analyze_instance(session, instance)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(work, ordered_instances))
    return [item for item in results if item is not None]


_list_refresh_inflight = False
_list_scan_inflight: Optional[threading.Event] = None


def _kick_off_refresh(
    bind, ordered_instances: list[ScenarioInstance]
) -> None:
    """One background recompute at a time — callers never wait on expiry."""
    global _list_refresh_inflight
    with _list_cache_lock:
        if _list_refresh_inflight:
            return
        _list_refresh_inflight = True

    def refresh() -> None:
        global _list_cache, _list_refresh_inflight  # noqa: PLW0603
        try:
            items = _scan_parallel(bind, ordered_instances)
            with _list_cache_lock:
                _list_cache = {
                    "entry": {"at": time.monotonic(), "items": items}
                }
        finally:
            with _list_cache_lock:
                _list_refresh_inflight = False

    threading.Thread(
        target=refresh, name="failures-list-cache-refresh", daemon=True
    ).start()


def _compute_or_join(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[FailureListItem]:
    """Cold compute with single-flight semantics.

    When the cache is empty (first request, or the startup warm-up is still
    running) exactly one scan runs and concurrent callers join it instead
    of duplicating the work and competing for database connections.
    """
    global _list_cache, _list_scan_inflight
    while True:
        with _list_cache_lock:
            entry = _list_cache.get("entry")
            if (
                entry is not None
                and time.monotonic() - entry["at"] < _LIST_CACHE_TTL_SECONDS
            ):
                return entry["items"]
            event = _list_scan_inflight
            if event is None:
                event = threading.Event()
                _list_scan_inflight = event
                owner = True
            else:
                owner = False
        if owner:
            try:
                items = _scan_parallel(bind, ordered_instances)
                with _list_cache_lock:
                    _list_cache = {
                        "entry": {"at": time.monotonic(), "items": items}
                    }
            finally:
                with _list_cache_lock:
                    _list_scan_inflight = None
                event.set()
            return items
        # Another scan (e.g. the startup warm-up) is already running — wait
        # for it to store its result instead of scanning in parallel.
        event.wait(timeout=120.0)


def _cached_dataset_items(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[FailureListItem]:
    """Memoized full detected list (PostgreSQL path only).

    - fresh entry  -> served immediately;
    - stale entry  -> served immediately (deterministic output is identical
      on the frozen seeded dataset) while one background thread recomputes,
      so a TTL expiry never strands a request on the multi-second scan;
    - no entry     -> computed once; concurrent callers and the startup
      warm-up join the in-flight scan rather than duplicating it.
    """
    global _list_cache
    with _list_cache_lock:
        entry = _list_cache.get("entry")
        if (
            entry is not None
            and time.monotonic() - entry["at"] < _LIST_CACHE_TTL_SECONDS
        ):
            return entry["items"]
        stale_items = entry["items"] if entry is not None else None
    if stale_items is not None:
        _kick_off_refresh(bind, ordered_instances)
        return stale_items
    return _compute_or_join(bind, ordered_instances)


def _dataset_items(
    session: Session, ordered_instances: list[ScenarioInstance]
) -> list[FailureListItem]:
    """Detected compound failures across the dataset (deterministic).

    Only payments carrying a FAILED-capable marker are deep-analyzed; the
    rest cannot be compound failures. The scan is bounded by the seeded
    dataset and documented as such — it is not an unbounded table scan.
    On PostgreSQL the scan is threaded and briefly memoized so the
    /failures page stays responsive; other engines run sequentially.
    """
    bind = session.get_bind()
    if getattr(bind, "dialect", None) is not None and bind.dialect.name == "postgresql":
        return _cached_dataset_items(bind, ordered_instances)
    return _scan_sequential(session, ordered_instances)


def list_failures(
    session: Session,
    limit: int,
    offset: int,
    severity: Optional[str] = None,
    failure_type: Optional[str] = None,
    outcome: Optional[str] = None,
    scope: Optional[str] = None,
) -> tuple[list[FailureListItem], int]:
    """Detected compound failures across the dataset (deterministic)."""
    outcome_filter = outcome
    detected_items = _dataset_items(session, _marker_ordered_instances(session))
    filtered = [
        item
        for item in detected_items
        if (not severity or item.severity == severity.upper())
        and (
            not failure_type
            or item.primary_failure_kind == failure_type.upper()
        )
        # Every detected compound failure carries a FAILED outcome, so any
        # other outcome filter intentionally returns nothing.
        and (not outcome_filter or outcome_filter.upper() == "FAILED")
        and (
            not scope or item.scope == scope.upper().replace("-", "_")
        )
    ]
    return filtered[offset:offset + limit], len(filtered)


def warm_failures_cache() -> None:
    """Best-effort background warm of the dataset scan (production).

    Called once at application startup on PostgreSQL so the first /failures
    page load is instant instead of paying the full deterministic scan.
    Never raises — a cold cache simply recomputes on first request.
    """
    try:
        from app.core.database import get_session_factory

        session = get_session_factory()()
        try:
            if session.get_bind().dialect.name != "postgresql":
                return
            _cached_dataset_items(
                session.get_bind(), _marker_ordered_instances(session)
            )
        finally:
            session.close()
    except Exception:  # noqa: BLE001 - warm-up must never break startup
        pass
