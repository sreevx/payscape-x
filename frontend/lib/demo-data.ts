/**
 * PAYSCAPE-X demo data layer.
 *
 * A few illustrative widgets (dashboard KPIs, the sample Action Center
 * queue, sample notifications) still draw values from this module. Real
 * product data — transactions, outcomes, failure patterns, simulations and
 * the event stream — comes from the backend API. ACTIVE_INVESTIGATIONS
 * references real seeded transactions (deterministic seed 42) so every
 * investigation entry opens the live pipeline on the transaction detail
 * page.
 *
 * Timestamps are relative to DEMO_NOW so the UI stays deterministic.
 */

import type {
  ActionQueueItem,
  ActiveInvestigation,
  ActivityItem,
  AppNotification,
  DemoTransaction,
  EventExplorerRow,
  FailurePattern,
  KpiSummary,
  OutcomeSlice,
  SimulationPreset,
  TransactionDetail,
  TransactionEventRow,
} from "@/types/demo";

export const DEMO_NOW = "2026-09-03T10:30:00Z";

/* ------------------------------------------------------------------ */
/* KPI summary                                                         */
/* ------------------------------------------------------------------ */

export const KPI_SUMMARY: KpiSummary[] = [
  {
    id: "kpi_payment_success",
    label: "Payment Success",
    value: "98.4%",
    delta: "+0.3 pts vs last week",
    tone: "info",
    description: "Share of payment attempts that succeeded",
  },
  {
    id: "kpi_outcome_success",
    label: "Business Outcome Success",
    value: "94.1%",
    delta: "-0.6 pts vs last week",
    tone: "success",
    description: "Successful payments that reached the intended outcome",
  },
  {
    id: "kpi_at_risk",
    label: "At Risk",
    value: "3.7%",
    delta: "+0.4 pts vs last week",
    tone: "warning",
    description: "Payments captured but the outcome is in doubt",
  },
  {
    id: "kpi_failed_outcomes",
    label: "Failed Outcomes",
    value: "2.2%",
    delta: "-0.1 pts vs last week",
    tone: "danger",
    description: "Captured payments that did not achieve the outcome",
  },
];

/* ------------------------------------------------------------------ */
/* Outcome distribution (chart placeholder)                            */
/* ------------------------------------------------------------------ */

export const OUTCOME_DISTRIBUTION: OutcomeSlice[] = [
  { label: "FULFILLED", value: 94.1, tone: "success", note: "Outcome verified across all stages" },
  { label: "AT_RISK", value: 3.7, tone: "warning", note: "Outcome not yet confirmed" },
  { label: "FAILED", value: 2.2, tone: "danger", note: "Outcome definitively not achieved" },
  { label: "UNVERIFIABLE", value: 0.0, tone: "neutral", note: "Insufficient event evidence" },
];

/* ------------------------------------------------------------------ */
/* Transactions (enriched demo rows)                                   */
/* ------------------------------------------------------------------ */

export const TRANSACTIONS: DemoTransaction[] = [
  { id: "payx_9f2b3c4d", orderId: "ORD-2026-10421", merchant: "Acme Retail", customerName: "Rahul Sharma", customerEmail: "rahul.sharma@example.com", amount: "2499.00", currency: "INR", provider: "razorpay", paymentStatus: "succeeded", outcome: "FULFILLED", risk: "low", lastEvent: "delivery.delivered", updatedAt: "2026-09-03T10:25:00Z" },
  { id: "payx_7a1d8e2f", orderId: "ORD-2026-10422", merchant: "Acme Retail", customerName: "Priya Patel", customerEmail: "priya.patel@example.com", amount: "8999.00", currency: "INR", provider: "razorpay", paymentStatus: "succeeded", outcome: "AT_RISK", risk: "high", lastEvent: "inventory.out_of_stock", updatedAt: "2026-09-03T09:04:00Z" },
  { id: "payx_5c9e0f1a", orderId: "ORD-2026-10423", merchant: "Northwind Foods", customerName: "Daniel Kim", customerEmail: "daniel.kim@example.com", amount: "42.50", currency: "USD", provider: "stripe", paymentStatus: "succeeded", outcome: "FULFILLED", risk: "low", lastEvent: "delivery.delivered", updatedAt: "2026-09-03T08:47:00Z" },
  { id: "payx_3e7b2a9c", orderId: "ORD-2026-10424", merchant: "Northwind Foods", customerName: "Maria Garcia", customerEmail: "maria.garcia@example.com", amount: "19.99", currency: "USD", provider: "stripe", paymentStatus: "succeeded", outcome: "AT_RISK", risk: "medium", lastEvent: "delivery.in_transit", updatedAt: "2026-09-03T09:31:00Z" },
  { id: "payx_8d4f6c0b", orderId: "ORD-2026-10425", merchant: "Cloudline SaaS", customerName: "Amit Verma", customerEmail: "amit.verma@example.com", amount: "149.00", currency: "USD", provider: "stripe", paymentStatus: "succeeded", outcome: "FAILED", risk: "critical", lastEvent: "delivery.failed", updatedAt: "2026-09-03T08:10:00Z" },
  { id: "payx_2b6e4d8f", orderId: "ORD-2026-10426", merchant: "Acme Retail", customerName: "Sofia Rossi", customerEmail: "sofia.rossi@example.com", amount: "120.00", currency: "EUR", provider: "stripe", paymentStatus: "succeeded", outcome: "UNVERIFIABLE", risk: "medium", lastEvent: "order.created", updatedAt: "2026-09-03T07:20:00Z" },
  { id: "payx_6c0a9e3d", orderId: "ORD-2026-10427", merchant: "Northwind Foods", customerName: "Tom Becker", customerEmail: "tom.becker@example.com", amount: "8.75", currency: "USD", provider: "stripe", paymentStatus: "succeeded", outcome: "FULFILLED", risk: "low", lastEvent: "delivery.delivered", updatedAt: "2026-09-03T06:58:00Z" },
  { id: "payx_4a8f2c7e", orderId: "ORD-2026-10428", merchant: "Acme Retail", customerName: "Neha Gupta", customerEmail: "neha.gupta@example.com", amount: "1199.00", currency: "INR", provider: "razorpay", paymentStatus: "succeeded", outcome: "AT_RISK", risk: "high", lastEvent: "inventory.out_of_stock", updatedAt: "2026-09-03T09:12:00Z" },
  { id: "payx_1e5b3d9a", orderId: "ORD-2026-10429", merchant: "Cloudline SaaS", customerName: "James Wilson", customerEmail: "james.wilson@example.com", amount: "49.00", currency: "USD", provider: "stripe", paymentStatus: "failed", outcome: "FAILED", risk: "critical", lastEvent: "payment.failed", updatedAt: "2026-09-03T08:55:00Z" },
  { id: "payx_0c7e5b8d", orderId: "ORD-2026-10430", merchant: "Acme Retail", customerName: "Aisha Khan", customerEmail: "aisha.khan@example.com", amount: "4599.00", currency: "INR", provider: "razorpay", paymentStatus: "refunded", outcome: "FAILED", risk: "high", lastEvent: "payment.refunded", updatedAt: "2026-09-03T07:55:00Z" },
  { id: "payx_9d2a6f4c", orderId: "ORD-2026-10431", merchant: "Northwind Foods", customerName: "Lena Fischer", customerEmail: "lena.fischer@example.com", amount: "34.20", currency: "EUR", provider: "stripe", paymentStatus: "succeeded", outcome: "FULFILLED", risk: "low", lastEvent: "delivery.delivered", updatedAt: "2026-09-03T05:40:00Z" },
  { id: "payx_5f8b1d7a", orderId: "ORD-2026-10432", merchant: "Cloudline SaaS", customerName: "Rohan Das", customerEmail: "rohan.das@example.com", amount: "249.00", currency: "USD", provider: "stripe", paymentStatus: "pending", outcome: "UNVERIFIABLE", risk: "medium", lastEvent: "payment.pending", updatedAt: "2026-09-03T09:48:00Z" },
  { id: "payx_7b3e9c5d", orderId: "ORD-2026-10433", merchant: "Acme Retail", customerName: "Emily Chen", customerEmail: "emily.chen@example.com", amount: "2999.00", currency: "INR", provider: "razorpay", paymentStatus: "succeeded", outcome: "AT_RISK", risk: "medium", lastEvent: "fulfillment.shipped", updatedAt: "2026-09-03T08:33:00Z" },
  { id: "payx_6d0a8f2b", orderId: "ORD-2026-10434", merchant: "Northwind Foods", customerName: "Omar Farouk", customerEmail: "omar.farouk@example.com", amount: "63.90", currency: "USD", provider: "stripe", paymentStatus: "succeeded", outcome: "FULFILLED", risk: "low", lastEvent: "delivery.delivered", updatedAt: "2026-09-02T18:12:00Z" },
];

/* ------------------------------------------------------------------ */
/* Transaction event scripts (per outcome archetype)                   */
/* ------------------------------------------------------------------ */

type EventScriptStep = readonly [
  eventType: string,
  source: string,
  summary: string,
  minutesBeforeLastEvent: number,
];

const EVENT_SCRIPTS: Record<string, { steps: EventScriptStep[]; notes: string[] }> = {
  fulfilled: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 150],
      ["payment.succeeded", "razorpay webhook", "Payment captured successfully", 148],
      ["inventory.allocated", "inventory service", "Stock allocated for all line items", 120],
      ["fulfillment.shipped", "fulfillment service", "Order handed to carrier — AWB assigned", 90],
      ["delivery.in_transit", "delivery partner", "Shipment in transit via regional hub", 60],
      ["delivery.delivered", "delivery partner", "Delivered and signed for", 5],
    ],
    notes: [
      "No anomalies detected across payment, inventory, fulfillment and delivery events.",
      "Outcome verified: the intended business result was achieved end-to-end.",
    ],
  },
  out_of_stock: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 140],
      ["payment.succeeded", "razorpay webhook", "Payment captured successfully", 138],
      ["inventory.out_of_stock", "inventory service", "Out of stock at capture — 2 line items", 60],
    ],
    notes: [
      "Payment succeeded but stock allocation failed at capture time.",
      "Order is queued for restock; outcome cannot be confirmed until fulfillment starts.",
    ],
  },
  shipping_delayed: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 200],
      ["payment.succeeded", "stripe webhook", "Payment captured successfully", 198],
      ["inventory.allocated", "inventory service", "Stock allocated for all line items", 170],
      ["fulfillment.shipped", "fulfillment service", "Order handed to carrier — AWB assigned", 150],
      ["delivery.in_transit", "delivery partner", "Shipment in transit via regional hub", 130],
      ["delivery.in_transit", "delivery partner", "Carrier delay — re-routed via alternate hub", 15],
    ],
    notes: [
      "Carrier delay detected after successful capture. Delivery SLA at risk.",
      "Monitoring window extended; outcome currently AT RISK.",
    ],
  },
  delivery_failed: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 300],
      ["payment.succeeded", "stripe webhook", "Payment captured successfully", 298],
      ["inventory.allocated", "inventory service", "Stock allocated for all line items", 270],
      ["fulfillment.shipped", "fulfillment service", "Order handed to carrier — AWB assigned", 240],
      ["delivery.in_transit", "delivery partner", "Shipment in transit via regional hub", 210],
      ["delivery.failed", "delivery partner", "Package reported lost in transit", 30],
    ],
    notes: [
      "Package lost in transit after a successful payment capture.",
      "Business outcome FAILED — refund flow initiated, awaiting provider confirmation.",
    ],
  },
  payment_failed: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 90],
      ["payment.failed", "stripe webhook", "Payment declined — insufficient funds", 88],
    ],
    notes: [
      "Payment was declined; no business outcome was ever initiated.",
      "Classified as FAILED at the payment stage — nothing to investigate downstream.",
    ],
  },
  unverifiable: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 320],
      ["payment.succeeded", "stripe webhook", "Payment captured successfully", 318],
    ],
    notes: [
      "No fulfillment or delivery events received within the monitoring window.",
      "Insufficient evidence to confirm the outcome — flagged UNVERIFIABLE.",
    ],
  },
  refunded: {
    steps: [
      ["order.created", "orders service", "Order placed and confirmed", 260],
      ["payment.succeeded", "razorpay webhook", "Payment captured successfully", 258],
      ["inventory.allocated", "inventory service", "Stock allocated for all line items", 230],
      ["fulfillment.shipped", "fulfillment service", "Order handed to carrier — AWB assigned", 200],
      ["delivery.failed", "delivery partner", "Recipient not reachable — returned to sender", 45],
      ["payment.refunded", "razorpay webhook", "Refund initiated for full amount", 10],
    ],
    notes: [
      "Delivery failed after multiple attempts; order returned to sender.",
      "Refund initiated for the full amount. Outcome FAILED for the original intent.",
    ],
  },
};

function archetypeFor(transaction: DemoTransaction): string {
  if (transaction.paymentStatus === "failed") return "payment_failed";
  if (transaction.paymentStatus === "refunded") return "refunded";
  if (transaction.outcome === "FULFILLED") return "fulfilled";
  if (transaction.outcome === "FAILED") return "delivery_failed";
  if (transaction.outcome === "UNVERIFIABLE") return "unverifiable";
  // AT_RISK — pick the script matching the last event
  return transaction.lastEvent === "inventory.out_of_stock"
    ? "out_of_stock"
    : "shipping_delayed";
}

function buildEvents(transaction: DemoTransaction): TransactionEventRow[] {
  const archetype = EVENT_SCRIPTS[archetypeFor(transaction)];
  const lastAt = new Date(transaction.updatedAt).getTime();
  return archetype.steps.map(([eventType, source, summary, minutesBefore], index) => ({
    id: `evt_${transaction.id}_${index + 1}`,
    transactionId: transaction.id,
    eventType,
    source,
    summary,
    timestamp: new Date(lastAt - minutesBefore * 60_000).toISOString(),
  }));
}

const DETAIL_NOTES: Record<string, string[]> = Object.fromEntries(
  Object.entries(EVENT_SCRIPTS).map(([key, value]) => [key, value.notes])
);

export function getTransactionDetail(id: string): TransactionDetail | undefined {
  const transaction = TRANSACTIONS.find((tx) => tx.id === id);
  if (!transaction) return undefined;

  const archetype = archetypeFor(transaction);
  const notes =
    DETAIL_NOTES[archetype] ??
    ["No notes available for this transaction."];

  return {
    transaction,
    events: buildEvents(transaction),
    authorized: transaction.amount,
    captured: transaction.paymentStatus === "succeeded" || transaction.paymentStatus === "refunded" ? transaction.amount : "—",
    refunded: transaction.paymentStatus === "refunded" ? transaction.amount : "—",
    notes,
  };
}

/* ------------------------------------------------------------------ */
/* Active investigations                                               */
/* ------------------------------------------------------------------ */

// Real seeded transactions with detected failures (deterministic seed 42,
// verified against the live backend). Each row opens the live investigation
// artifact — the full deterministic pipeline on the transaction page.
export const ACTIVE_INVESTIGATIONS: ActiveInvestigation[] = [
  { id: "inv_compound", transactionId: "a80fd436-7c48-527b-b36b-16f3e52992ed", amount: "4545.00", currency: "INR", paymentStatus: "succeeded", outcome: "FAILED", risk: "critical", lastEvent: "CUSTOMER_COMPLAINT", updatedAt: "2026-09-04T21:28:00Z" },
  { id: "inv_inventory", transactionId: "cb200bee-8610-5ec6-954c-5c62eb78c059", amount: "3998.00", currency: "INR", paymentStatus: "succeeded", outcome: "FAILED", risk: "high", lastEvent: "NO_FULFILLMENT", updatedAt: "2026-09-01T01:28:00Z" },
  { id: "inv_delivery", transactionId: "cf1b7910-4070-5ce0-9dce-d78ba304371b", amount: "2497.00", currency: "INR", paymentStatus: "succeeded", outcome: "FAILED", risk: "high", lastEvent: "CUSTOMER_MESSAGE_RECEIVED", updatedAt: "2026-09-03T14:18:00Z" },
];



/* ------------------------------------------------------------------ */
/* Failure patterns                                                    */
/* ------------------------------------------------------------------ */

export const FAILURE_PATTERNS: FailurePattern[] = [
  {
    id: "fp_paid_unfulfilled",
    name: "Paid, Not Fulfilled",
    description: "Payments captured but no fulfillment event within the SLA window.",
    transactions: 14,
    impact: "Revenue at risk",
    trend: "rising",
    status: "monitoring",
    firstSeen: "2026-08-18T00:00:00Z",
  },
  {
    id: "fp_delivery_exception",
    name: "Delivery Exceptions",
    description: "Successful payments with failed or returned deliveries.",
    transactions: 9,
    impact: "Refund + logistics cost",
    trend: "rising",
    status: "emerging",
    firstSeen: "2026-08-21T00:00:00Z",
  },
  {
    id: "fp_inventory_oversell",
    name: "Inventory Oversell",
    description: "Payments succeeded while stock was unavailable at capture time.",
    transactions: 6,
    impact: "Customer churn risk",
    trend: "stable",
    status: "monitoring",
    firstSeen: "2026-08-12T00:00:00Z",
  },
  {
    id: "fp_refund_reconcile",
    name: "Refund Reconciliation Lag",
    description: "Refunds initiated but not confirmed by the provider within SLA.",
    transactions: 5,
    impact: "Cash-flow friction",
    trend: "declining",
    status: "monitoring",
    firstSeen: "2026-08-25T00:00:00Z",
  },
];

/* ------------------------------------------------------------------ */
/* Recent activity                                                     */
/* ------------------------------------------------------------------ */

export const RECENT_ACTIVITY: ActivityItem[] = [
  { id: "act_01", kind: "investigation", message: "Investigation opened for ORD-2026-1145 — compound failure spanning payment, inventory and delivery stages", timestamp: "2026-09-04T22:00:00Z", transactionId: "a80fd436-7c48-527b-b36b-16f3e52992ed" },
  { id: "act_02", kind: "event", message: "5,240 structured events ingested in the last hour across 4 providers", timestamp: "2026-09-03T09:00:00Z" },
  { id: "act_03", kind: "pattern", message: "Failure pattern “Paid, Not Fulfilled” crossed its alert threshold", timestamp: "2026-09-03T08:40:00Z" },
  { id: "act_04", kind: "outcome", message: "Outcome FAILED assigned to ORD-2026-1132 — refund initiated", timestamp: "2026-09-02T11:30:00Z", transactionId: "1485c755-f2e6-5d19-a845-02ba7d623751" },
  { id: "act_05", kind: "refund", message: "Refund confirmed for ORD-2026-1132 (₹6,194.00)", timestamp: "2026-09-02T12:05:00Z", transactionId: "1485c755-f2e6-5d19-a845-02ba7d623751" },
  { id: "act_06", kind: "alert", message: "Delivery partner reported SLA breach on 3 in-transit shipments", timestamp: "2026-09-03T07:30:00Z" },
];

/* ------------------------------------------------------------------ */
/* Notifications                                                       */
/* ------------------------------------------------------------------ */

export const NOTIFICATIONS: AppNotification[] = [
  { id: "ntf_1", title: "Outcome at risk", body: "payx_7a1d8e2f — paid but out of stock at capture.", timestamp: "2026-09-03T10:25:00Z", unread: true, tone: "warning" },
  { id: "ntf_2", title: "Failed outcome", body: "payx_8d4f6c0b — delivery failed after capture.", timestamp: "2026-09-03T10:05:00Z", unread: true, tone: "danger" },
  { id: "ntf_3", title: "Pattern updated", body: "Paid, Not Fulfilled — 14 transactions this week.", timestamp: "2026-09-03T09:30:00Z", unread: false, tone: "info" },
  { id: "ntf_4", title: "Event ingestion resumed", body: "Structured event stream reconnected.", timestamp: "2026-09-03T08:00:00Z", unread: false, tone: "neutral" },
];

/* ------------------------------------------------------------------ */
/* Action center                                                       */
/* ------------------------------------------------------------------ */

export const ACTION_QUEUE: ActionQueueItem[] = [
  { id: "act_a1", transactionId: "payx_8d4f6c0b", kind: "Refund review", priority: "critical", status: "in_review", assignedTo: "Operations Analyst", createdAt: "2026-09-03T08:12:00Z" },
  { id: "act_a2", transactionId: "payx_0c7e5b8d", kind: "Refund confirmation", priority: "high", status: "needs_approval", assignedTo: "Ops Lead", createdAt: "2026-09-03T07:57:00Z" },
  { id: "act_a3", transactionId: "payx_7a1d8e2f", kind: "Restock & re-fulfillment", priority: "high", status: "queued", assignedTo: "Inventory Ops", createdAt: "2026-09-03T09:06:00Z" },
  { id: "act_a4", transactionId: "payx_4a8f2c7e", kind: "Customer outreach", priority: "medium", status: "queued", assignedTo: "Support", createdAt: "2026-09-03T09:14:00Z" },
  { id: "act_a5", transactionId: "payx_5f8b1d7a", kind: "Payment verification", priority: "medium", status: "in_review", assignedTo: "Operations Analyst", createdAt: "2026-09-03T09:51:00Z" },
  { id: "act_a6", transactionId: "payx_7b3e9c5d", kind: "Fulfillment check", priority: "low", status: "queued", assignedTo: "Fulfillment Ops", createdAt: "2026-09-03T08:35:00Z" },
];

/* ------------------------------------------------------------------ */
/* Event explorer                                                      */
/* ------------------------------------------------------------------ */

export const EVENT_STREAM: EventExplorerRow[] = [
  { id: "evt_s_1", eventType: "payment.succeeded", transactionId: "payx_9f2b3c4d", source: "razorpay webhook", summary: "Payment captured — ₹2,499.00", timestamp: "2026-09-03T10:20:00Z" },
  { id: "evt_s_2", eventType: "inventory.out_of_stock", transactionId: "payx_7a1d8e2f", source: "inventory service", summary: "Out of stock at capture — 2 line items", timestamp: "2026-09-03T09:04:00Z" },
  { id: "evt_s_3", eventType: "payment.pending", transactionId: "payx_5f8b1d7a", source: "stripe webhook", summary: "Settlement pending — $249.00", timestamp: "2026-09-03T09:48:00Z" },
  { id: "evt_s_4", eventType: "delivery.failed", transactionId: "payx_8d4f6c0b", source: "delivery partner", summary: "Package reported lost in transit", timestamp: "2026-09-03T08:10:00Z" },
  { id: "evt_s_5", eventType: "payment.refunded", transactionId: "payx_0c7e5b8d", source: "razorpay webhook", summary: "Refund initiated for full amount", timestamp: "2026-09-03T07:55:00Z" },
  { id: "evt_s_6", eventType: "delivery.delivered", transactionId: "payx_5c9e0f1a", source: "delivery partner", summary: "Delivered and signed for", timestamp: "2026-09-03T08:47:00Z" },
  { id: "evt_s_7", eventType: "fulfillment.shipped", transactionId: "payx_7b3e9c5d", source: "fulfillment service", summary: "Order handed to carrier — AWB assigned", timestamp: "2026-09-03T08:33:00Z" },
  { id: "evt_s_8", eventType: "payment.failed", transactionId: "payx_1e5b3d9a", source: "stripe webhook", summary: "Payment declined — insufficient funds", timestamp: "2026-09-03T08:55:00Z" },
  { id: "evt_s_9", eventType: "delivery.in_transit", transactionId: "payx_3e7b2a9c", source: "delivery partner", summary: "Carrier delay — re-routed via alternate hub", timestamp: "2026-09-03T09:31:00Z" },
  { id: "evt_s_10", eventType: "order.created", transactionId: "payx_2b6e4d8f", source: "orders service", summary: "Order placed and confirmed", timestamp: "2026-09-03T07:20:00Z" },
];

/* ------------------------------------------------------------------ */
/* Simulation presets (placeholder — engine arrives in Part 3)         */
/* ------------------------------------------------------------------ */

export const SIMULATION_PRESETS: SimulationPreset[] = [
  { id: "sim_baseline", name: "Baseline — Normal Day", description: "Current event mix, no disruptions.", availability: "Available in Part 3" },
  { id: "sim_payment_failure", name: "Payment Failure Spike", description: "Provider success rate drops by 30% for 2 hours.", availability: "Available in Part 3" },
  { id: "sim_inventory_outage", name: "Inventory Outage", description: "Top-selling SKU unavailable at capture time.", availability: "Available in Part 3" },
  { id: "sim_delivery_partner", name: "Delivery Partner Outage", description: "One carrier stops scanning shipments for 6 hours.", availability: "Available in Part 3" },
];

/* ------------------------------------------------------------------ */
/* User / profile (demo)                                               */
/* ------------------------------------------------------------------ */

export const DEMO_USER = {
  name: "Operations Analyst",
  email: "operator@payscape-x.local",
  initials: "OA",
  role: "Risk Operations",
};