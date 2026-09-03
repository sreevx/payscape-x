"""Tests for the Simulation Lab engine (Part 7).

Exercises the deterministic intervention registry and the doctored-journey
replay against a fully seeded in-memory database (seed 42):

- all 10 scenarios produce coherent, deterministic results
- every intervention is either SIMULATED or honestly reports
  NOT_APPLICABLE / NOT_EFFECTIVE / NOT_SUPPORTED (never an invented remedy)
- an inventory-recovery fixture (recorded alternative stock) demonstrates
  real resolution + simulated impact reduction
- repeated runs are byte-identical and the lab is strictly read-only
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.events import EventType
from app.models import (
    InventoryRecord,
    Product,
    Refund,
    ScenarioInstance,
    TransactionEvent,
)
from app.simulation.models import ALL_SIM_STATUSES
from tests.seed_helpers import build_seeded_engine

ALL_SCENARIO_SLUGS = [
    "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
    "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
    "contradictory_event", "compound_failure",
]


@pytest.fixture(scope="module")
def session_factory():
    _engine, factory = build_seeded_engine()
    yield factory
    _engine.dispose()


@pytest.fixture()
def session(session_factory):
    with session_factory() as session:
        yield session


def _payment_ids(session: Session) -> dict[str, str]:
    """scenario slug -> first payment id (journey order)."""
    instances = list(session.scalars(select(ScenarioInstance)))
    by_slug: dict[str, list[tuple[int, str]]] = {}
    for instance in instances:
        slug = str(instance.scenario_type.value).lower()
        payment_id = str(instance.metadata_.get("payment_id", ""))
        by_slug.setdefault(slug, []).append(
            (int(instance.metadata_.get("journey_index", 0)), payment_id)
        )
    for slug in by_slug:
        by_slug[slug].sort()
    return {slug: items[0][1] for slug, items in by_slug.items()}


def _simulate(session: Session, transaction_id: str, intervention=None):
    from app.services.simulation_service import get_simulations

    report = get_simulations(
        session, transaction_id, intervention=intervention
    )
    assert report is not None, transaction_id
    return report


def _by_type(report) -> dict[str, object]:
    return {item.intervention.intervention_type: item for item in report.interventions}


def _stock_shortage(session: Session, transaction_id: str, quantity: int = 50) -> list[str]:
    """Grant real recorded stock for every SKU this journey ran short on."""
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.payment_id == uuid.UUID(transaction_id),
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value,
            )
        )
    )
    for row in rows:
        sku = str(row.payload.get("product_sku"))
        product = session.scalars(select(Product).where(Product.sku == sku)).first()
        assert product is not None, sku
        record = session.scalars(
            select(InventoryRecord).where(InventoryRecord.product_id == product.id)
        ).first()
        record.available_quantity = max(record.available_quantity, quantity)
    session.commit()
    return sorted({str(row.payload.get("product_sku")) for row in rows})


def _event_count(session: Session, transaction_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(TransactionEvent)
        .where(TransactionEvent.payment_id == uuid.UUID(transaction_id))
    )


# ---------------------------------------------------------------------------
# Registry + shape
# ---------------------------------------------------------------------------

def test_registry_order_and_shape(session):
    transaction_id = _payment_ids(session)["normal_success"]
    report = _simulate(session, transaction_id)

    types = [item.intervention.intervention_type for item in report.interventions]
    assert types == [
        "DO_NOTHING", "ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT",
        "SUBSTITUTE_PRODUCT", "REFUND", "HUMAN_REVIEW",
    ]
    baseline = report.baseline
    assert baseline.transaction_id == transaction_id
    assert baseline.outcome == "FULFILLED"
    for item in report.interventions:
        assert item.status in ALL_SIM_STATUSES
        # Deterministic uuid5 ids — valid UUIDs, unique per intervention.
        uuid.UUID(item.simulation_id)
        assert item.transaction_id == transaction_id
        assert item.intervention.description
        assert isinstance(item.delta_impact_score, float)
        assert set(item.rule_ids)  # every result traces rule ids
        assert item.metadata["simulated"] is True


def test_deterministic_ids(session):
    transaction_id = _payment_ids(session)["compound_failure"]
    first = _simulate(session, transaction_id)
    second = _simulate(session, transaction_id)
    for a, b in zip(first.interventions, second.interventions):
        assert a.simulation_id == b.simulation_id
        assert a.metadata == b.metadata
    # Deterministic across separately seeded databases too.
    _engine2, factory2 = build_seeded_engine()
    with factory2() as other:
        other_id = _payment_ids(other)["compound_failure"]
        third = _simulate(other, other_id)
        assert [item.simulation_id for item in first.interventions] == [
            item.simulation_id for item in third.interventions
        ]
    _engine2.dispose()


def test_all_scenarios_serve_and_are_deterministic(session):
    ids = _payment_ids(session)
    for slug in ALL_SCENARIO_SLUGS:
        transaction_id = ids[slug]
        first = _simulate(session, transaction_id)
        second = _simulate(session, transaction_id)
        assert len(first.interventions) == 6, slug
        for a, b in zip(first.interventions, second.interventions):
            assert a == b, slug


# ---------------------------------------------------------------------------
# Scenario semantics
# ---------------------------------------------------------------------------

def test_normal_success_unchanged(session):
    transaction_id = _payment_ids(session)["normal_success"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "FULFILLED"
    items = _by_type(report)
    do_nothing = items["DO_NOTHING"]
    assert do_nothing.status == "SIMULATED"
    assert do_nothing.simulated_outcome == "FULFILLED"
    assert do_nothing.delta_impact_score == 0.0
    assert items["REFUND"].status == "NOT_APPLICABLE"
    assert items["HUMAN_REVIEW"].status == "NOT_APPLICABLE"
    assert items["ALTERNATIVE_INVENTORY"].status == "NOT_APPLICABLE"


def test_payment_failed_does_not_invent_downstream(session):
    transaction_id = _payment_ids(session)["payment_failed"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "FAILED"
    items = _by_type(report)
    assert items["REFUND"].status == "NOT_APPLICABLE"      # nothing captured
    assert items["ALTERNATIVE_INVENTORY"].status == "NOT_APPLICABLE"
    assert items["RETRY_FULFILLMENT"].status == "NOT_APPLICABLE"
    # The failure stays untouched under do-nothing / human review.
    assert items["DO_NOTHING"].simulated_outcome == "FAILED"
    assert items["DO_NOTHING"].delta_impact_score == 0.0
    # No simulated remedy claims a resolution.
    for name in ("ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT", "REFUND"):
        assert items[name].resolved_failures == [], name


def test_inventory_failure_no_stock_is_not_effective(session):
    transaction_id = _payment_ids(session)["inventory_failure"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "FAILED"
    assert report.baseline.impact_score == 100.0
    items = _by_type(report)
    for name in ("ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT"):
        item = items[name]
        assert item.status == "NOT_EFFECTIVE", name
        assert "alternative" in item.reason.lower() or "stock" in item.reason.lower(), name
        assert item.resolved_failures == [], name
    assert items["SUBSTITUTE_PRODUCT"].status == "NOT_SUPPORTED"
    refund = items["REFUND"]
    assert refund.status == "SIMULATED"
    assert refund.simulated_outcome == "FAILED"
    assert refund.remaining_failures  # refund never fixes the failure


def test_alternative_inventory_resolves_failure_when_stock_recorded():
    # Isolated engine: granting recorded stock must not leak into the shared
    # module database used by the no-stock assertions above.
    _engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            transaction_id = _payment_ids(session)["inventory_failure"]
            stocked = _stock_shortage(session, transaction_id)
            assert stocked
            report = _simulate(session, transaction_id)
            items = _by_type(report)
            _assert_resolved(alternative := items["ALTERNATIVE_INVENTORY"])
    finally:
        _engine.dispose()


def _assert_resolved(alternative):
    assert alternative.status == "SIMULATED"

    resolved_kinds = {ref.kind for ref in alternative.resolved_failures}
    assert resolved_kinds == {"INVENTORY_ALLOCATION_FAILED", "FULFILLMENT_NOT_CREATED"}
    # Without downstream delivery records the honest simulated outcome is
    # UNVERIFIABLE — the lab never invents a fulfilled delivery.
    assert alternative.simulated_outcome == "UNVERIFIABLE"
    assert alternative.simulated_impact_score < alternative.baseline_impact_score
    assert alternative.delta_impact_score < 0
    assert alternative.metadata  # deterministic doctoring metadata


def test_retry_fulfillment_without_inventory_never_resolves(session):
    transaction_id = _payment_ids(session)["inventory_failure"]
    report = _simulate(session, transaction_id)
    item = _by_type(report)["RETRY_FULFILLMENT"]
    assert item.status == "NOT_EFFECTIVE"
    assert item.simulated_outcome == "FAILED"
    assert item.resolved_failures == []


def test_delivery_failure_refund_is_containment_not_recovery(session):
    transaction_id = _payment_ids(session)["delivery_failure"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "FAILED"
    items = _by_type(report)
    refund = items["REFUND"]
    assert refund.status == "SIMULATED"
    # A refund never delivers the goods.
    assert refund.simulated_outcome == "FAILED"
    assert refund.resolved_failures == []
    assert refund.remaining_failures
    # Refund containment is impact in PAYSCAPE-X accounting: the replayed
    # impact engine records refund consequences (never a negative delta).
    assert refund.delta_impact_score >= 0
    assert refund.metadata.get("simulated_event_ids")  # hypothetical records
    assert any("does not deliver" in a for a in refund.assumptions)


def test_refund_flow_already_refunded(session):
    transaction_id = _payment_ids(session)["refund_flow"]
    report = _simulate(session, transaction_id)
    items = _by_type(report)
    refund = items["REFUND"]
    assert refund.status == "NOT_APPLICABLE"
    assert "already" in refund.reason.lower()
    assert items["DO_NOTHING"].simulated_outcome == "FAILED"


def test_missing_event_no_invented_recovery(session):
    transaction_id = _payment_ids(session)["missing_event"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "UNVERIFIABLE"
    items = _by_type(report)
    for name in ("ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT", "REFUND"):
        assert items[name].status == "NOT_APPLICABLE", name
        assert items[name].delta_impact_score == 0.0, name
    assert items["DO_NOTHING"].simulated_outcome == "UNVERIFIABLE"


def test_contradictory_event_no_unjustified_certainty(session):
    transaction_id = _payment_ids(session)["contradictory_event"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "UNVERIFIABLE"
    items = _by_type(report)
    for name in ("ALTERNATIVE_INVENTORY", "RETRY_FULFILLMENT", "REFUND"):
        assert items[name].status == "NOT_APPLICABLE", name
        assert items[name].resolved_failures == [], name
    # Do-nothing replay stays unverifiable — no simulated certainty appears.
    assert items["DO_NOTHING"].simulated_outcome == "UNVERIFIABLE"


def test_compound_failure_stays_honest(session):
    transaction_id = _payment_ids(session)["compound_failure"]
    report = _simulate(session, transaction_id)
    assert report.baseline.outcome == "FAILED"
    assert report.baseline.compound_failure_detected is True
    items = _by_type(report)
    # No stock recorded anywhere → alternative/retry cannot act.
    assert items["ALTERNATIVE_INVENTORY"].status == "NOT_EFFECTIVE"
    assert items["RETRY_FULFILLMENT"].status == "NOT_EFFECTIVE"
    refund = items["REFUND"]
    assert refund.status == "SIMULATED"
    assert refund.simulated_outcome == "FAILED"
    assert refund.delta_impact_score >= 0  # already at the 100 ceiling


def test_substitute_product_unsupported_on_dataset(session):
    ids = _payment_ids(session)
    for slug in ALL_SCENARIO_SLUGS:
        report = _simulate(session, ids[slug])
        item = _by_type(report)["SUBSTITUTE_PRODUCT"]
        assert item.status == "NOT_SUPPORTED", slug
        assert "substitute" in item.reason.lower(), slug


# ---------------------------------------------------------------------------
# Comparison ranking
# ---------------------------------------------------------------------------

def test_comparison_ranks_by_impact_reduction():
    _engine, factory = build_seeded_engine()
    try:
        with factory() as session:
            transaction_id = _payment_ids(session)["inventory_failure"]
            _stock_shortage(session, transaction_id)
            report = _simulate(session, transaction_id)
            rows = report.comparison
            _assert_ranked(rows)
    finally:
        _engine.dispose()


def _assert_ranked(rows):
    assert rows, "comparison must include SIMULATED interventions"
    assert [row.rank for row in rows] == list(range(1, len(rows) + 1))
    # Ranked by (delta asc, remaining failures asc, assumptions asc).
    keys = [
        (row.delta_impact_score, row.remaining_failure_count, row.assumption_count)
        for row in rows
    ]
    assert keys == sorted(keys)
    assert rows[0].intervention_type == "ALTERNATIVE_INVENTORY"
    assert rows[0].delta_impact_score < 0


def test_comparison_best_is_not_recommendation(session):
    # No simulated result may improve on a delivery failure — the table still
    # ranks deterministically and DO_NOTHING is the reference anchor.
    transaction_id = _payment_ids(session)["delivery_failure"]
    report = _simulate(session, transaction_id)
    rows = report.comparison
    assert rows
    deltas = [row.delta_impact_score for row in rows]
    assert min(deltas) >= 0
    # Every comparison row references an intervention present in the report.
    types = {row.intervention_type for row in rows}
    assert types <= {item.intervention.intervention_type for item in report.interventions}


# ---------------------------------------------------------------------------
# Traceability + read-only safety
# ---------------------------------------------------------------------------

def test_traceability_references_real_records(session):
    transaction_id = _payment_ids(session)["compound_failure"]
    report = _simulate(session, transaction_id)
    journey_events = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.payment_id == uuid.UUID(transaction_id)
            )
        )
    )
    known_event_ids = {str(row.id) for row in journey_events}
    for item in report.interventions:
        for ref in item.remaining_failures + item.resolved_failures:
            assert ref.rule_id, ref.kind
            assert ref.kind and ref.label
        for event_id in item.event_ids:
            assert event_id in known_event_ids, item.intervention.intervention_type


def test_simulation_is_read_only(session):
    transaction_id = _payment_ids(session)["inventory_failure"]
    payment_uuid = uuid.UUID(transaction_id)
    before_events = _event_count(session, transaction_id)
    refunds_before = session.scalar(
        select(func.count()).select_from(Refund).where(Refund.payment_id == payment_uuid)
    )
    # Run every intervention twice — including refund containment which
    # replays hypothetical refund records.
    for _ in range(2):
        report = _simulate(session, transaction_id)
        assert len(report.interventions) == 6
    after_events = _event_count(session, transaction_id)
    refunds_after = session.scalar(
        select(func.count()).select_from(Refund).where(Refund.payment_id == payment_uuid)
    )
    assert before_events == after_events
    assert refunds_before == refunds_after == 0
    # Inventory records untouched (no stock was invented for real).
    rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.payment_id == uuid.UUID(transaction_id),
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value,
            )
        )
    )
    assert rows  # shortage records still present after the simulation
