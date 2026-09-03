"""PAYSCAPE-X synthetic dataset command line.

Usage:
    python -m app.seed                # seed the database (deterministic, seed=42)
    python -m app.seed --seed 7       # different deterministic dataset
    python -m app.seed --reset        # clear existing synthetic data first
    python -m app.seed --validate     # structural validation only
    python -m app.seed --validate --reset

`--reset` is destructive and refuses to run unless APP_ENV is an explicit
development/demo/test environment, so it can never be triggered
accidentally against a production database.
"""

import argparse
import logging
import sys

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, get_session_factory
from app.core.logging import configure_logging
from app.synthetic.generator import DEFAULT_SEED, DatasetGenerator
from app.synthetic.scenarios import SCENARIO_DEFINITIONS

# Tables are cleared children-first (FK-safe order).
CLEAR_ORDER = [
    "transaction_events",
    "scenario_instances",
    "webhooks",
    "refunds",
    "customer_messages",
    "delivery_events",
    "shipments",
    "fulfillment_events",
    "fulfillments",
    "inventory_events",
    "inventory_records",
    "products",
    "payments",
    "orders",
    "customers",
    "merchants",
]

logger = logging.getLogger("app.seed")


def clear_dataset(session: Session) -> None:
    """Delete every synthetic row (children first)."""
    settings = get_settings()
    if settings.app_env not in {"development", "demo", "test"}:
        raise SystemExit(
            f"Refusing to reset: APP_ENV is '{settings.app_env}', not a "
            "development/demo/test environment. Set APP_ENV=development to "
            "reset synthetic data."
        )
    for table_name in CLEAR_ORDER:
        session.execute(delete(Base.metadata.tables[table_name]))
    session.commit()
    logger.info("Cleared %s tables", len(CLEAR_ORDER))


def run_seed(seed: int, reset: bool = False) -> dict:
    """Generate and persist the synthetic dataset. Returns the summary."""
    factory = get_session_factory()
    with factory() as session:
        if reset:
            clear_dataset(session)

        generator = DatasetGenerator(seed)
        dataset = generator.generate()

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
        return dataset.summarize()


def print_summary(summary: dict) -> None:
    print("PAYSCAPE-X Synthetic Dataset")
    print("----------------------------")
    print(f"Merchant: {summary['merchant']}")
    print()
    print(f"Customers: {summary['customers']}")
    print(f"Products: {summary['products']}")
    print(f"Orders: {summary['orders']}")
    print(f"Payments: {summary['payments']}")
    print(f"Transaction Events: {summary['transaction_events']}")
    print()
    print("Scenarios:")
    for definition in SCENARIO_DEFINITIONS:
        name = definition.scenario_type.value.replace("_", " ").title()
        print(f"  {name}: {summary['scenario_counts'].get(definition.scenario_type.value, 0)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed PAYSCAPE-X with deterministic synthetic data."
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED,
        help="RNG seed (default 42). Same seed → same dataset.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear existing synthetic data before seeding (dev/demo only).",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate structural integrity of the current dataset instead of seeding.",
    )
    args = parser.parse_args()

    configure_logging(get_settings().log_level)

    if args.validate:
        from app.services.validation import print_validation_report

        factory = get_session_factory()
        with factory() as session:
            problem_count, _ = print_validation_report(session)
        return 1 if problem_count else 0

    summary = run_seed(args.seed, reset=args.reset)
    print_summary(summary)
    logger.info("Seeded with seed=%s", args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())