"""Read-only dashboard summary service.

GET /api/v1/summary aggregates the seeded dataset for the dashboard:

- payment lifecycle counts come straight from the `payments` table;
- outcome counts come from the EXACT Part 5 deterministic path the
  per-transaction outcome endpoint uses (journey -> evidence ->
  consistency -> outcome), run over every scenario instance. There is no
  second outcome calculation: each instance is classified by
  `outcome_service.build_outcome` on the same loaded inputs the
  outcome route would build.

The per-journey classification is IO-bound on PostgreSQL (many round-trips
to the database), so — exactly like the proven /failures dataset scan
(`failures_service`) — the scan runs across a small thread pool with one
session/connection per worker and is memoized for a short TTL. Non-
PostgreSQL engines (the in-memory SQLite test suite) keep the sequential
single-session path. Output is a pure function of the seeded records and
is deterministic across processes and databases.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import PaymentStatus
from app.models import Payment, ScenarioInstance
from app.schemas.summary import OutcomeCounts, SummaryResponse
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.outcome_service import build_outcome

# A payment that reached a terminal capture counts as a payment success,
# whether or not it was later refunded. Anything still CREATED/AUTHORIZED
# is pending (not a success, not a failure).
_SUCCESSFUL_PAYMENT_STATUSES = frozenset(
    {
        PaymentStatus.CAPTURED.value,
        PaymentStatus.REFUNDED.value,
        PaymentStatus.PARTIALLY_REFUNDED.value,
    }
)

_SOURCE = (
    "Deterministic outcome engine (Part 5) over every seeded journey — "
    "read-only, no second outcome calculation."
)

_SCAN_THREADS = 10
_CACHE_TTL_SECONDS = 300
_cache_lock = threading.Lock()
_cache: dict = {}
_refresh_inflight = False
_scan_inflight: Optional[threading.Event] = None


def _kick_off_refresh(
    bind, ordered_instances: list[ScenarioInstance]
) -> None:
    """One background recompute at a time — callers never wait on expiry."""
    global _refresh_inflight
    with _cache_lock:
        if _refresh_inflight:
            return
        _refresh_inflight = True

    def refresh() -> None:
        global _cache, _refresh_inflight  # noqa: PLW0603
        try:
            outcomes = _scan_parallel(bind, ordered_instances)
            with _cache_lock:
                _cache = {
                    "outcomes": {"at": time.monotonic(), "outcomes": outcomes}
                }
        finally:
            with _cache_lock:
                _refresh_inflight = False

    threading.Thread(
        target=refresh, name="summary-cache-refresh", daemon=True
    ).start()


def _compute_or_join(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[str]:
    """Cold compute with single-flight semantics.

    When the cache is empty (first request, or the startup warm-up is still
    running) exactly one scan runs and concurrent callers join it instead
    of duplicating the work and competing for database connections.
    """
    global _cache, _scan_inflight
    while True:
        with _cache_lock:
            entry = _cache.get("outcomes")
            if (
                entry is not None
                and time.monotonic() - entry["at"] < _CACHE_TTL_SECONDS
            ):
                return entry["outcomes"]
            event = _scan_inflight
            if event is None:
                event = threading.Event()
                _scan_inflight = event
                owner = True
            else:
                owner = False
        if owner:
            try:
                outcomes = _scan_parallel(bind, ordered_instances)
                with _cache_lock:
                    _cache = {
                        "outcomes": {
                            "at": time.monotonic(),
                            "outcomes": outcomes,
                        }
                    }
            finally:
                with _cache_lock:
                    _scan_inflight = None
                event.set()
            return outcomes
        # Another scan (e.g. the startup warm-up) is already running — wait
        # for it to store its result instead of scanning in parallel.
        event.wait(timeout=120.0)


# ---------------------------------------------------------------------------
# One-journey classification
# ---------------------------------------------------------------------------

def _ordered_instances(session: Session) -> list[ScenarioInstance]:
    """Every scenario instance, in deterministic journey order."""
    instances = [
        instance
        for instance in session.scalars(select(ScenarioInstance))
        if instance.metadata_.get("payment_id")
    ]

    def instance_key(instance: ScenarioInstance):
        return int(instance.metadata_.get("journey_index", 0))

    return sorted(instances, key=instance_key)


def _classify_instance(session: Session, instance: ScenarioInstance) -> Optional[str]:
    """Run the exact Part 5 outcome path for one journey.

    Returns the outcome value (FULFILLED / AT_RISK / FAILED / UNVERIFIABLE)
    or None when the journey cannot be reconstructed (should not happen for
    seeded instances).
    """
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
    return build_outcome(journey, integrity, evidence, consistency).outcome


# ---------------------------------------------------------------------------
# Scan: threaded on PostgreSQL, sequential elsewhere
# ---------------------------------------------------------------------------

def _scan_sequential(
    session: Session, ordered_instances: list[ScenarioInstance]
) -> list[str]:
    """Single-session scan (non-PostgreSQL engines, tests)."""
    outcomes: list[str] = []
    for instance in ordered_instances:
        outcome = _classify_instance(session, instance)
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


def _scan_parallel(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[str]:
    """Threaded scan with one session/connection per worker. Deterministic:
    results are reassembled in input order and each outcome is a pure
    function of its records, so the output equals the sequential scan."""
    factory = sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)
    workers = max(1, min(_SCAN_THREADS, len(ordered_instances)))

    def work(instance: ScenarioInstance) -> Optional[str]:
        session = factory()
        try:
            return _classify_instance(session, instance)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(work, ordered_instances))
    return [outcome for outcome in results if outcome is not None]


def _cached_outcomes(
    bind, ordered_instances: list[ScenarioInstance]
) -> list[str]:
    """Memoized outcome scan (PostgreSQL path only).

    - fresh entry  -> served immediately;
    - stale entry  -> served immediately (deterministic output is identical
      on the frozen seeded dataset) while one background thread recomputes,
      so a TTL expiry never strands a request on the multi-second scan;
    - no entry     -> computed once; concurrent callers and the startup
      warm-up join the in-flight scan rather than duplicating it.
    """
    global _cache
    with _cache_lock:
        entry = _cache.get("outcomes")
        if (
            entry is not None
            and time.monotonic() - entry["at"] < _CACHE_TTL_SECONDS
        ):
            return entry["outcomes"]
        stale = entry["outcomes"] if entry is not None else None
    if stale is not None:
        _kick_off_refresh(bind, ordered_instances)
        return stale
    return _compute_or_join(bind, ordered_instances)


def _dataset_outcomes(
    session: Session, ordered_instances: list[ScenarioInstance]
) -> list[str]:
    """Classify every journey (memoized on PostgreSQL, TTL-bounded)."""
    bind = session.get_bind()
    if getattr(bind, "dialect", None) is None or bind.dialect.name != "postgresql":
        return _scan_sequential(session, ordered_instances)
    return _cached_outcomes(bind, ordered_instances)


# ---------------------------------------------------------------------------
# Payment lifecycle aggregates (cheap direct queries)
# ---------------------------------------------------------------------------

def _payment_counts(session: Session) -> tuple[int, int, int]:
    """(success, failed, pending) payment counts across the dataset."""
    rows = session.execute(
        select(Payment.status, func.count(Payment.id)).group_by(Payment.status)
    ).all()
    success = failed = pending = 0
    for status, count in rows:
        if status in _SUCCESSFUL_PAYMENT_STATUSES:
            success += count
        elif status == PaymentStatus.FAILED.value:
            failed += count
        else:
            pending += count
    return success, failed, pending


# ---------------------------------------------------------------------------
# Public entry point + startup warm-up
# ---------------------------------------------------------------------------

def get_summary(session: Session) -> SummaryResponse:
    """Real dashboard aggregates (read-only, deterministic)."""
    instances = _ordered_instances(session)
    outcome_values = _dataset_outcomes(session, instances)
    total = len(outcome_values)

    fulfilled = outcome_values.count("FULFILLED")
    at_risk = outcome_values.count("AT_RISK")
    failed = outcome_values.count("FAILED")
    unverifiable = outcome_values.count("UNVERIFIABLE")

    success, failed_payments, pending = _payment_counts(session)

    def rate(count: int) -> float:
        return round(count * 100.0 / total, 1) if total else 0.0

    return SummaryResponse(
        total_transactions=total,
        payment_success_count=success,
        payment_failed_count=failed_payments,
        payment_pending_count=pending,
        payment_success_rate=rate(success),
        payment_failed_rate=rate(failed_payments),
        outcomes=OutcomeCounts(
            fulfilled=fulfilled,
            at_risk=at_risk,
            failed=failed,
            unverifiable=unverifiable,
        ),
        fulfilled_rate=rate(fulfilled),
        at_risk_rate=rate(at_risk),
        failed_rate=rate(failed),
        unverifiable_rate=rate(unverifiable),
        source=_SOURCE,
        computed_at=datetime.now(timezone.utc),
    )


def warm_summary_cache() -> None:
    """Best-effort background warm of the aggregate scan (production).

    Called once at application startup on PostgreSQL so the first
    /api/v1/summary request is instant instead of paying the full
    deterministic scan. Never raises — a cold cache simply recomputes on
    the first request.
    """
    try:
        from app.core.database import get_session_factory

        session = get_session_factory()()
        try:
            if session.get_bind().dialect.name != "postgresql":
                return
            _dataset_outcomes(session, _ordered_instances(session))
        finally:
            session.close()
    except Exception:  # noqa: BLE001 - warm-up must never break startup
        pass
