"""Simulation Lab service (Part 7).

Composition layer between the API routes and the deterministic
`app.simulation` engine. It loads the full pipeline used by the analysis
package (journey -> evidence -> consistency -> outcome -> compound failure
-> impact), plus the deterministic data facts the lab needs:

- webhooks (for the integrity replay over doctored journey views)
- cross-transaction view (same shared-SKU cohort used by Part 6)
- per-SKU stock availability / requested quantity (final InventoryRecord
  snapshot — the lab never guesses about stock)

The engine then replays every intervention over private in-memory journey
views. Returns None for unknown transaction ids (the route turns that into
404) and for unknown intervention types (the POST route turns that into
400). The lab is strictly read-only.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import EventType
from app.models import InventoryRecord, Product, TransactionEvent
from app.schemas.simulation import (
    CompareItem,
    FailureRefItem,
    InterventionItem,
    RiskRefItem,
    SimulationBaselineItem,
    SimulationReport,
    SimulationResultItem,
)
from app.services import journeys_service
from app.services.consistency_service import build_consistency
from app.services.domain_context import load_domain_context
from app.services.evidence_service import build_evidence
from app.services.failures_service import build_failure
from app.services.impact_service import (
    build_impact,
    load_cross_transaction,
)
from app.services.outcome_service import build_outcome
from app.simulation.engine import simulate


@dataclass
class InventoryFacts:
    """Deterministic stock facts loaded for one transaction."""

    shortage_skus: list[str] = field(default_factory=list)
    requested_by_sku: dict = field(default_factory=dict)
    inventory_available: dict = field(default_factory=dict)
    substitute_by_sku: dict = field(default_factory=dict)


def _resolve_transaction_id(transaction_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(transaction_id)
    except (ValueError, AttributeError):
        return None


def load_inventory_facts(session: Session, payment_uuid: uuid.UUID) -> InventoryFacts:
    """Load the OUT_OF_STOCK facts + final availability for the payment.

    Availability comes from the product's InventoryRecord (the generator's
    final snapshot). The simulation may only assume alternative stock when
    this record shows enough available quantity — it never invents stock.
    """
    shortage_rows = list(
        session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.event_type == EventType.INVENTORY_OUT_OF_STOCK.value,
                TransactionEvent.payment_id == payment_uuid,
            )
        )
    )
    requested_by_sku: dict[str, int] = {}
    for row in shortage_rows:
        payload = row.payload or {}
        sku = str(payload.get("product_sku", ""))
        if not sku:
            continue
        requested = payload.get("requested") or payload.get("quantity") or 1
        try:
            requested = int(requested)
        except (TypeError, ValueError):
            requested = 1
        requested_by_sku[sku] = max(requested_by_sku.get(sku, 0), requested)

    facts = InventoryFacts(shortage_skus=sorted(requested_by_sku))
    facts.requested_by_sku = requested_by_sku
    if not requested_by_sku:
        return facts

    products = {
        product.sku: product
        for product in session.scalars(
            select(Product).where(Product.sku.in_(list(requested_by_sku)))
        )
    }
    if products:
        records = {
            str(record.product_id): record.available_quantity
            for record in session.scalars(
                select(InventoryRecord).where(
                    InventoryRecord.product_id.in_(
                        [product.id for product in products.values()]
                    )
                )
            )
        }
        facts.inventory_available = {
            sku: records.get(str(product.id), 0)
            for sku, product in products.items()
            if product is not None
        }
    # The synthetic catalogue records no substitute-product relationships;
    # kept as an explicit extension point for future catalogues.
    facts.substitute_by_sku = {}
    return facts


# ---------------------------------------------------------------------------
# Schema mapping
# ---------------------------------------------------------------------------

def _failure_ref_item(ref) -> FailureRefItem:
    return FailureRefItem(kind=ref.kind, label=ref.label, rule_id=ref.rule_id)


def _baseline_schema(baseline) -> SimulationBaselineItem:
    return SimulationBaselineItem(
        transaction_id=baseline.transaction_id,
        outcome=baseline.outcome,
        confidence=baseline.confidence,
        consistency_status=baseline.consistency_status,
        compound_failure_detected=baseline.compound_failure_detected,
        severity=baseline.severity,
        impact_score=baseline.impact_score,
        impact_scope=baseline.impact_scope,
        affected_transactions=baseline.affected_transactions,
        root_causes=[_failure_ref_item(ref) for ref in baseline.root_causes],
        event_ids=list(baseline.event_ids),
        evidence_ids=list(baseline.evidence_ids),
    )


def _result_schema(result) -> SimulationResultItem:
    return SimulationResultItem(
        simulation_id=result.simulation_id,
        transaction_id=result.transaction_id,
        status=result.status,
        reason=result.reason,
        intervention=InterventionItem(
            intervention_type=result.intervention.intervention_type,
            label=result.intervention.label,
            description=result.intervention.description,
        ),
        baseline_outcome=result.baseline_outcome,
        baseline_confidence=result.baseline_confidence,
        simulated_outcome=result.simulated_outcome,
        simulated_confidence=result.simulated_confidence,
        baseline_impact_score=result.baseline_impact_score,
        simulated_impact_score=result.simulated_impact_score,
        delta_impact_score=result.delta_impact_score,
        resolved_failures=[_failure_ref_item(ref) for ref in result.resolved_failures],
        remaining_failures=[_failure_ref_item(ref) for ref in result.remaining_failures],
        new_risks=[
            RiskRefItem(claim=risk.claim, rule_id=risk.rule_id,
                        classification=risk.classification)
            for risk in result.new_risks
        ],
        assumptions=list(result.assumptions),
        event_ids=list(result.event_ids),
        evidence_ids=list(result.evidence_ids),
        rule_ids=list(result.rule_ids),
        metadata=dict(result.metadata),
    )


def _report_schema(report) -> SimulationReport:
    return SimulationReport(
        transaction_id=report.transaction_id,
        baseline=_baseline_schema(report.baseline),
        interventions=[_result_schema(item) for item in report.interventions],
        comparison=[
            _comparison_schema(item) for item in report.comparison
        ],
    )


def _comparison_schema(item):
    return CompareItem(
        rank=item.rank,
        intervention_type=item.intervention_type,
        label=item.label,
        status=item.status,
        simulated_outcome=item.simulated_outcome,
        simulated_impact_score=item.simulated_impact_score,
        delta_impact_score=item.delta_impact_score,
        remaining_failure_count=item.remaining_failure_count,
        assumption_count=item.assumption_count,
    )


# ---------------------------------------------------------------------------
# Service entry points
# ---------------------------------------------------------------------------

def _load_pipeline(session: Session, transaction_id: str):
    """Load the full deterministic pipeline for one transaction.

    Returns (journey, integrity, evidence, consistency, outcome, failure,
    impact, context, webhooks, cross, inventory_facts) or None when the
    transaction is unknown.
    """
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
    failure = build_failure(journey, integrity, evidence, consistency, outcome)
    cross = load_cross_transaction(session, payment_uuid)
    impact = build_impact(
        journey, integrity, evidence, consistency, outcome, failure, cross
    )
    webhooks = journeys_service._load_webhooks(session, payment_uuid)
    inventory_facts = load_inventory_facts(session, payment_uuid)
    return (
        journey, integrity, evidence, consistency, outcome, failure, impact,
        context, webhooks, cross, inventory_facts,
    )


def get_simulations(
    session: Session, transaction_id: str, intervention: Optional[str] = None
) -> Optional[SimulationReport]:
    """Simulation report for one transaction (all or one intervention)."""
    loaded = _load_pipeline(session, transaction_id)
    if loaded is None:
        return None
    (journey, integrity, evidence, consistency, outcome, failure, impact,
     context, webhooks, cross, inventory_facts) = loaded
    report = simulate(
        journey, integrity, evidence, consistency, outcome, failure, impact,
        context, webhooks, cross, inventory_facts,
        intervention_type=intervention,
    )
    if report is None:
        return None
    return _report_schema(report)


def get_single_result(
    session: Session, transaction_id: str, intervention: str
) -> Optional[SimulationResultItem]:
    """Run one intervention. None: unknown transaction (routes 404)."""
    report = get_simulations(session, transaction_id, intervention=intervention)
    if report is None:
        return None
    return report.interventions[0]
