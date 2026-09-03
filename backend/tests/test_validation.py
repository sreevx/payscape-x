"""Tests for the structural data-integrity validator.

The validator must only flag STRUCTURAL problems (broken references, missing
correlation ids, inconsistent amounts). It must NOT judge business-state
correctness — intentionally generated scenarios (missing events,
contradictions, delayed webhooks) are valid data.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.enums import ScenarioType
from app.models import (
    CustomerMessage,
    ScenarioInstance,
    TransactionEvent,
)
from app.services.validation import print_validation_report, validate_dataset
from app.synthetic.generator import DatasetGenerator


@pytest.fixture(scope="module")
def seeded_session():
    """Full deterministic dataset persisted in an in-memory SQLite db."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        dataset = DatasetGenerator(seed=42).generate()
        session.add_all(
            [dataset.merchant]
            + dataset.customers
            + dataset.products
            + dataset.inventory_records
            + dataset.records
            + dataset.unified
            + dataset.instances
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_full_dataset_is_structurally_sound(seeded_session):
    problems = validate_dataset(seeded_session)
    assert problems == [], "\n".join(problems)


def test_print_report_counts_every_entity(seeded_session, capsys):
    problem_count, _ = print_validation_report(seeded_session)
    assert problem_count == 0
    out = capsys.readouterr().out
    for expected in ("Merchants:", "Orders:", "Transaction events:",
                     "Scenario instances:"):
        assert expected in out
    assert "No integrity problems found." in out


def test_validator_flags_orphan_references(seeded_session):
    """A message pointing at a nonexistent customer is caught."""
    bogus_customer = uuid.uuid4()
    orphan = CustomerMessage(
        customer_id=bogus_customer,
        order_id=uuid.uuid4(),  # also bogus — must not point at a real order
        channel="EMAIL",
        direction="INBOUND",
        message="ghost",
        timestamp=datetime.now(timezone.utc),
        metadata_={},
    )
    seeded_session.add(orphan)
    seeded_session.flush()  # SQLite does not enforce FKs by default

    problems = validate_dataset(seeded_session)
    seeded_session.rollback()

    assert any("customer_message" in p and "invalid customer_id" in p
               for p in problems)
    assert any("invalid order_id" in p for p in problems)


def test_validator_flags_orphan_scenario_correlation(seeded_session):
    """A unified event whose correlation matches no scenario is caught."""
    orphan_event = TransactionEvent(
        order_id=uuid.uuid4(),
        payment_id=None,
        event_type="ORDER_CREATED",
        source="ORDER_SERVICE",
        timestamp=datetime.now(timezone.utc),
        correlation_id=uuid.uuid4(),  # not a scenario correlation
        idempotency_key=None,
        payload={},
    )
    seeded_session.add(orphan_event)
    seeded_session.flush()

    problems = validate_dataset(seeded_session)
    seeded_session.rollback()

    assert any("correlation_id does not match any scenario" in p
               for p in problems)


def test_validator_never_judges_business_state(seeded_session):
    """Contradictory/missing/delayed scenarios must pass without warnings.

    The validator may not know or care that a payment was 'captured then
    failed', that a webhook never arrived, or that a delivery was returned.
    Those are business-state questions for the future Consistency Engine.
    """
    problems = validate_dataset(seeded_session)
    types = set(
        seeded_session.scalars(select(ScenarioInstance.scenario_type)).all()
    )
    # The interesting scenarios exist in the dataset...
    assert ScenarioType.CONTRADICTORY_EVENT in types
    assert ScenarioType.MISSING_EVENT in types
    assert ScenarioType.COMPOUND_FAILURE in types
    # ...and none of them produced structural problems.
    assert problems == []
