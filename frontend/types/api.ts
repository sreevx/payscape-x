/**
 * API response types — mirror the backend read schemas
 * (backend/app/schemas/*). Keep aligned when the API evolves.
 *
 * Statuses/event types arrive in the backend's UPPER_SNAKE vocabulary
 * (e.g. "CAPTURED", "ORDER_CREATED") rather than the demo layer's
 * lowercase labels.
 */

export type ApiPaymentStatus =
  | "CREATED"
  | "AUTHORIZED"
  | "CAPTURED"
  | "FAILED"
  | "REFUNDED"
  | "PARTIALLY_REFUNDED";

export interface ApiTransactionListItem {
  id: string;
  order_id: string;
  external_order_id: string;
  customer_name: string;
  customer_email: string;
  amount: string;
  currency: string;
  payment_status: ApiPaymentStatus;
  provider: string;
  method: string | null;
  scenario_type: string | null;
  scenario_slug: string | null;
  event_count: number;
  created_at: string;
}

export interface ApiTransactionListResponse {
  items: ApiTransactionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiEventItem {
  id: string;
  order_id: string;
  payment_id: string | null;
  event_type: string;
  source: string;
  timestamp: string;
  correlation_id: string;
  idempotency_key: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ApiTransactionDetail {
  id: string;
  order_id: string;
  external_order_id: string;
  customer_id: string;
  customer_name: string;
  customer_email: string;
  merchant_name: string;
  amount: string;
  currency: string;
  order_status: string;
  payment_status: ApiPaymentStatus;
  provider: string;
  provider_payment_id: string;
  method: string | null;
  captured_at: string | null;
  created_at: string;
  scenario_type: string | null;
  scenario_slug: string | null;
  scenario_description: string | null;
  events: ApiEventItem[];
}

export interface ApiEventStreamItem {
  id: string;
  order_id: string;
  external_order_id: string;
  payment_id: string | null;
  event_type: string;
  source: string;
  timestamp: string;
  correlation_id: string;
  idempotency_key: string | null;
  payload: Record<string, unknown>;
}

export interface ApiEventStreamResponse {
  items: ApiEventStreamItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiScenarioSummary {
  scenario_id: string;
  scenario_type: string;
  name: string;
  description: string;
  transaction_count: number;
  event_count: number;
}

export interface ApiScenarioTransactionItem {
  id: string;
  order_id: string;
  external_order_id: string;
  customer_name: string;
  amount: string;
  currency: string;
  payment_status: string;
  created_at: string;
}

export interface ApiTimelineEventItem {
  event_type: string;
  source: string;
  timestamp: string;
  correlation_id: string;
}

export interface ApiScenarioDetail {
  scenario_id: string;
  scenario_type: string;
  name: string;
  description: string;
  correlation_count: number;
  event_count: number;
  transactions: ApiScenarioTransactionItem[];
  timeline: ApiTimelineEventItem[];
}

/** One unified event as part of a reconstructed journey (Part 3). */
export interface ApiJourneyEvent {
  id: string;
  order_id: string;
  payment_id: string | null;
  event_type: string;
  source: string;
  timestamp: string;
  correlation_id: string;
  idempotency_key: string | null;
  payload: Record<string, unknown>;
  ingestion_position: number;
  is_duplicate: boolean;
  is_unknown: boolean;
  is_orphan: boolean;
  duplicate_of_event_id: string | null;
}

/** One deterministic journey graph node (Part 3). */
export interface ApiGraphNode {
  id: string;
  kind: "journey_root" | "correlation_root" | "event";
  label: string;
  event_type: string | null;
  timestamp: string | null;
  source: string | null;
  correlation_id: string | null;
  payload_ref: string | null;
  position: { x: number; y: number };
}

/** One deterministic journey graph edge (Part 3). */
export interface ApiGraphEdge {
  source: string;
  target: string;
  relationship_type: "PRECEDES" | "TRIGGERS" | "BELONGS_TO" | "CORRELATES_WITH" | "DERIVED_FROM";
  rule_id: string;
  reason: string;
}

/** The reconstructed journey graph (Part 3). */
export interface ApiJourneyGraph {
  transaction_id: string;
  correlation_id: string | null;
  layout: string;
  nodes: ApiGraphNode[];
  edges: ApiGraphEdge[];
}

/** Structural findings (Part 3) — observations only, never outcome verdicts. */
export interface ApiMissingCandidate {
  event_type: string;
  rule_id: string;
  note: string;
}

export interface ApiContradiction {
  type: string;
  rule_id: string;
  involved_event_ids: string[];
  timestamps: string[];
  explanation: string;
}

export interface ApiDuplicate {
  event_id: string;
  event_type: string;
  idempotency_key: string;
  canonical_event_id: string;
  rule_id: string;
}

export interface ApiOutOfOrderEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  ingestion_position: number;
  chronological_position: number;
}

export interface ApiDelayedEvent {
  event_id: string;
  event_type: string;
  delay_minutes: number | null;
}

export interface ApiUnknownEvent {
  event_id: string;
  event_type: string;
  reason: string;
}

export interface ApiOrphanEvent {
  event_id: string;
  event_type: string;
  correlation_id: string;
  reason: string;
}

/** Journey integrity report (Part 3). */
export interface ApiJourneyIntegrity {
  transaction_id: string;
  total_events: number;
  linked_events: number;
  orphan_count: number;
  duplicate_count: number;
  unknown_count: number;
  delayed_count: number;
  out_of_order_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
  duration_seconds: number | null;
  missing_expected_event_candidates: ApiMissingCandidate[];
  contradictions: ApiContradiction[];
  duplicates: ApiDuplicate[];
  out_of_order_events: ApiOutOfOrderEvent[];
  delayed_events: ApiDelayedEvent[];
  unknown_events: ApiUnknownEvent[];
  orphan_events: ApiOrphanEvent[];
}

/** The complete reconstructed journey (Part 3). */
export interface ApiJourney {
  transaction_id: string;
  order_id: string;
  payment_id: string;
  correlation_id: string | null;
  events: ApiJourneyEvent[];
  graph: ApiJourneyGraph;
  integrity: ApiJourneyIntegrity;
}

/** Evidence strength levels (Part 4) — deterministic, never AI-derived. */
export type ApiEvidenceStrength =
  | "DIRECT"
  | "CORROBORATED"
  | "INDIRECT"
  | "MISSING"
  | "CONTRADICTED";

/** One evidence item: a deterministic claim backed by concrete records (Part 4). */
export interface ApiEvidenceItem {
  evidence_id: string;
  category: string;
  claim: string;
  event_ids: string[];
  source: string;
  timestamp: string | null;
  supporting_data: Record<string, unknown>;
  strength: ApiEvidenceStrength;
  rule_id: string;
  confidence: number;
  contradictions: string[];
  metadata: Record<string, unknown>;
}

/** A structurally expected event type that was not observed (Part 4). */
export interface ApiEvidenceGap {
  event_type: string;
  rule_id: string;
  note: string;
}

/** Two mutually exclusive states both recorded, preserved not resolved (Part 4). */
export interface ApiEvidenceContradiction {
  contradiction_id: string;
  type: string;
  rule_id: string;
  event_ids: string[];
  explanation: string;
  severity: string;
}

/** The complete evidence report (Part 4). */
export interface ApiEvidenceReport {
  transaction_id: string;
  evidence: ApiEvidenceItem[];
  gaps: ApiEvidenceGap[];
  contradictions: ApiEvidenceContradiction[];
  strength_summary: Record<string, number>;
}

/** Consistency rule statuses (Part 4). */
export type ApiConsistencyStatus =
  | "PASS"
  | "VIOLATION"
  | "INSUFFICIENT_EVIDENCE"
  | "NOT_APPLICABLE";

/** One evaluated consistency rule (Part 4). */
export interface ApiConsistencyCheck {
  rule_id: string;
  name: string;
  description: string;
  severity: string;
  status: ApiConsistencyStatus;
  supporting_event_ids: string[];
  explanation: string;
}

/** The full consistency report (Part 4). overall_integrity is record
 * agreement only — it is NOT the business outcome. */
export interface ApiConsistencyResult {
  transaction_id: string;
  checks: ApiConsistencyCheck[];
  passed: string[];
  violations: string[];
  insufficient_evidence: string[];
  not_applicable: string[];
  overall_integrity: "CONSISTENT" | "INCONSISTENT" | "INSUFFICIENT_EVIDENCE";
}

/** The combined deterministic analysis package (Parts 4 + 5 + 6). */
export interface ApiAnalysis {
  transaction_id: string;
  journey: ApiJourney;
  evidence: ApiEvidenceReport;
  consistency: ApiConsistencyResult;
  outcome: ApiOutcome;
  compound_failure: ApiCompoundFailure;
  impact: ApiImpact;
}

/** Business outcome states (Part 5) — never to be confused with payment state. */
export type ApiBusinessOutcome =
  | "FULFILLED"
  | "AT_RISK"
  | "FAILED"
  | "UNVERIFIABLE";

/** One auditable outcome reason (Part 5). */
export interface ApiOutcomeReason {
  code: string;
  message: string;
  severity: string;
  rule_id: string;
  event_ids: string[];
  evidence_ids: string[];
}

/** One documented deterministic confidence adjustment (Part 5). */
export interface ApiConfidenceAdjustment {
  signal: string;
  delta: number;
  note: string;
}

/** One rule evaluation in the decision trace (Part 5). */
export interface ApiRuleTraceStep {
  rule_id: string;
  name: string;
  priority: number;
  outcome: string;
  applied: boolean;
  note: string;
}

/** The deterministic business-outcome classification (Part 5). */
export interface ApiOutcome {
  transaction_id: string;
  outcome: ApiBusinessOutcome;
  confidence: number;
  primary_reason: ApiOutcomeReason;
  reasons: ApiOutcomeReason[];
  supporting_evidence_ids: string[];
  supporting_event_ids: string[];
  blocking_evidence_ids: string[];
  consistency_status: string | null;
  evidence_completeness: number | null;
  rule_trace: ApiRuleTraceStep[];
  confidence_adjustments: ApiConfidenceAdjustment[];
}

/** Evidence labels used across Part 6 (mirror backend). */
export type ApiEvidenceStatus =
  | "OBSERVED"
  | "DERIVED"
  | "POTENTIAL";

/** One node of a failure chain (Part 6). */
export interface ApiFailureNode {
  node_id: string;
  kind: string;
  stage: string;
  label: string;
  status: "OBSERVED" | "DERIVED";
  message: string;
  rule_id: string;
  event_ids: string[];
  evidence_ids: string[];
  timestamp: string | null;
  metadata: Record<string, unknown>;
}

/** One deterministic failure-chain edge (Part 6). */
export interface ApiChainEdge {
  edge_id: string;
  source_node: string;
  target_node: string;
  relationship_type: "CAUSES" | "BLOCKS" | "LEADS_TO" | "PREVENTS" | "IMPACTS";
  rule_id: string;
  reason: string;
}

/** One deterministic root cause (Part 6). */
export interface ApiRootCause {
  root_cause_id: string;
  kind: string;
  label: string;
  stage: string;
  explanation: string;
  rule_id: string;
  event_ids: string[];
  evidence_ids: string[];
}

/** The compound-failure analysis for one transaction (Part 6). */
export interface ApiCompoundFailure {
  compound_failure_id: string;
  transaction_id: string;
  detected: boolean;
  reason: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  classification: "OBSERVED" | "DERIVED";
  primary_failure: ApiFailureNode | null;
  failure_chain: ApiFailureNode[];
  edges: ApiChainEdge[];
  root_causes: ApiRootCause[];
  confidence: number | null;
  event_ids: string[];
  evidence_ids: string[];
  metadata: Record<string, unknown>;
}

/** One consequence of the failure (Part 6) — never potential-as-fact. */
export interface ApiConsequence {
  consequence_id: string;
  category: string;
  claim: string;
  classification: ApiEvidenceStatus;
  rule_id: string;
  event_ids: string[];
  evidence_ids: string[];
  metadata: Record<string, unknown>;
}

/** Another transaction hit by the same shortage (Part 6). */
export interface ApiAffectedTransaction {
  transaction_id: string;
  order_id: string;
  external_order_id: string;
  scenario_type: string | null;
  scenario_slug: string | null;
  outcome: string | null;
  product_skus: string[];
  impact: "OBSERVED" | "INFERRED";
}

/** One documented impact-score contribution (Part 6). */
export interface ApiScoreComponent {
  signal: string;
  points: number;
  note: string;
}

/** The consequence / impact analysis for one transaction (Part 6). */
export interface ApiImpact {
  impact_id: string;
  transaction_id: string;
  scope: "SINGLE_TRANSACTION" | "MULTI_TRANSACTION";
  affected_transactions: number;
  affected_orders: number;
  affected_products: number;
  observed_consequences: ApiConsequence[];
  derived_consequences: ApiConsequence[];
  potential_consequences: ApiConsequence[];
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  impact_score: number;
  shared_skus: string[];
  shared_failure_patterns: string[];
  affected: ApiAffectedTransaction[];
  score_components: ApiScoreComponent[];
  event_ids: string[];
  evidence_ids: string[];
  metadata: Record<string, unknown>;
}

/** One detected compound failure in the dataset list (Part 6). */
export interface ApiFailureListItem {
  transaction_id: string;
  order_id: string;
  external_order_id: string;
  scenario_type: string | null;
  scenario_slug: string | null;
  outcome: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  classification: string;
  detected: boolean;
  primary_failure_kind: string | null;
  primary_failure_label: string | null;
  root_cause_kinds: string[];
  chain_length: number;
  distinct_stages: string[];
  confidence: number | null;
  scope: string;
  affected_transactions: number;
  shared_skus: string[];
}

/** Paginated detected compound failures (Part 6). */
export interface ApiFailureListResponse {
  items: ApiFailureListItem[];
  total: number;
  limit: number;
  offset: number;
}

/** One intervention offered by the Simulation Lab (Part 7). */
export interface ApiSimulationIntervention {
  intervention_type: string;
  label: string;
  description: string;
}

/** A deterministic failure reference (Part 7). */
export interface ApiSimulationFailureRef {
  kind: string;
  label: string;
  rule_id: string;
}

/** A deterministic risk reference in the simulated world (Part 7). */
export interface ApiSimulationRiskRef {
  claim: string;
  rule_id: string;
  classification: string;
}

/** The observed (ACTUAL) state every intervention is compared against (Part 7). */
export interface ApiSimulationBaseline {
  transaction_id: string;
  outcome: ApiBusinessOutcome;
  confidence: number;
  consistency_status: string | null;
  compound_failure_detected: boolean;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  impact_score: number;
  impact_scope: string;
  affected_transactions: number;
  root_causes: ApiSimulationFailureRef[];
  event_ids: string[];
  evidence_ids: string[];
}

/** Intervention result statuses (Part 7). */
export type ApiSimulationStatus =
  | "SIMULATED"
  | "NOT_APPLICABLE"
  | "NOT_EFFECTIVE"
  | "NOT_SUPPORTED";

/** The deterministic simulation of ONE intervention (Part 7). */
export interface ApiSimulationResult {
  simulation_id: string;
  transaction_id: string;
  status: ApiSimulationStatus;
  reason: string;
  intervention: ApiSimulationIntervention;
  baseline_outcome: ApiBusinessOutcome;
  baseline_confidence: number;
  simulated_outcome: ApiBusinessOutcome;
  simulated_confidence: number;
  baseline_impact_score: number;
  simulated_impact_score: number;
  delta_impact_score: number;
  resolved_failures: ApiSimulationFailureRef[];
  remaining_failures: ApiSimulationFailureRef[];
  new_risks: ApiSimulationRiskRef[];
  assumptions: string[];
  event_ids: string[];
  evidence_ids: string[];
  rule_ids: string[];
  metadata: Record<string, unknown>;
}

/** One row of the deterministic comparison table (Part 7). */
export interface ApiSimulationCompareItem {
  rank: number;
  intervention_type: string;
  label: string;
  status: ApiSimulationStatus;
  simulated_outcome: ApiBusinessOutcome;
  simulated_impact_score: number;
  delta_impact_score: number;
  remaining_failure_count: number;
  assumption_count: number;
}

/** The complete Simulation Lab report for one transaction (Part 7). */
export interface ApiSimulationReport {
  transaction_id: string;
  baseline: ApiSimulationBaseline;
  interventions: ApiSimulationResult[];
  comparison: ApiSimulationCompareItem[];
}

/** One alternative action the merchant could consider instead (Part 8). */
export interface ApiDecisionAlternative {
  action: string;
  reason: string;
}

/** The complete auditable AI decision for one transaction (Part 8). */
export interface ApiDecision {
  decision_id: string;
  transaction_id: string;
  /** LLM | DETERMINISTIC_FALLBACK */
  decision_source: string;
  /** DO_NOTHING | RECOVER_ROOT_CAUSE | REFUND_OR_CONTAIN | HUMAN_REVIEW */
  recommended_action: string;
  reason: string;
  decision_confidence: number;
  evidence_confidence: number;
  evidence_ids: string[];
  event_ids: string[];
  simulation_id: string | null;
  alternatives: ApiDecisionAlternative[];
  human_approval_required: boolean;
  /** PENDING | APPROVED | REJECTED */
  approval_status: string;
  rejection_reason: string | null;
  decided_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  metadata: Record<string, unknown>;
}

/** Event sources used by the unified stream (mirror backend EventSource). */
export const API_EVENT_SOURCES = [
  "PAYMENT_PROVIDER",
  "WEBHOOK",
  "ORDER_SERVICE",
  "INVENTORY_SERVICE",
  "FULFILLMENT_SERVICE",
  "DELIVERY_SERVICE",
  "CUSTOMER",
  "SYSTEM",
] as const;

/**
 * Event-type groups for the explorer filter — mirrors the backend
 * registry (backend/app/core/events.py). Keep in sync.
 */
export const API_EVENT_TYPE_GROUPS: Record<string, string[]> = {
  Order: [
    "ORDER_CREATED",
    "ORDER_CONFIRMED",
    "ORDER_CANCELLED",
    "ORDER_NOT_CONFIRMED",
  ],
  Payment: [
    "PAYMENT_CREATED",
    "PAYMENT_AUTHORIZED",
    "PAYMENT_CAPTURED",
    "PAYMENT_FAILED",
    "PAYMENT_REFUNDED",
  ],
  Webhook: [
    "WEBHOOK_SENT",
    "WEBHOOK_RECEIVED",
    "WEBHOOK_DELAYED",
    "WEBHOOK_DUPLICATE",
    "WEBHOOK_PROCESSING_FAILED",
  ],
  Inventory: [
    "INVENTORY_RESERVED",
    "INVENTORY_RELEASED",
    "INVENTORY_OUT_OF_STOCK",
    "INVENTORY_RESERVATION_EXPIRED",
    "INVENTORY_DECREMENTED",
  ],
  Fulfillment: [
    "FULFILLMENT_CREATED",
    "FULFILLMENT_PROCESSING",
    "FULFILLMENT_PACKED",
    "FULFILLMENT_SHIPPED",
    "FULFILLMENT_FAILED",
    "NO_FULFILLMENT",
  ],
  Delivery: [
    "SHIPMENT_CREATED",
    "SHIPMENT_IN_TRANSIT",
    "DELIVERY_OUT_FOR_DELIVERY",
    "DELIVERY_COMPLETED",
    "DELIVERY_FAILED",
    "DELIVERY_RETURNED",
  ],
  Customer: ["CUSTOMER_MESSAGE_RECEIVED", "CUSTOMER_COMPLAINT"],
  Refund: ["REFUND_INITIATED", "REFUND_COMPLETED", "REFUND_FAILED"],
};