/**
 * Demo-mode and UI-facing types.
 *
 * These types describe the handful of illustrative widgets (sample action
 * queue, notifications, activity/pattern cards) that still draw values
 * from `./lib/demo-data.ts`. Real product data — transactions, outcomes,
 * failure patterns, simulations, events and the dashboard summary — comes
 * from the backend API. They are intentionally separate from the shared
 * domain types in `./index.ts`.
 */

import type { Currency, PaymentStatus } from "./index";

export type { Currency, PaymentStatus } from "./index";

export type BusinessOutcome = "FULFILLED" | "AT_RISK" | "FAILED" | "UNVERIFIABLE";

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export interface KpiSummary {
  id: string;
  label: string;
  value: string;
  /** Optional trend/context line under the card — real KPIs omit it. */
  delta?: string;
  tone: Tone;
  description: string;
}

export interface DemoTransaction {
  id: string;
  orderId: string;
  merchant: string;
  customerName: string;
  customerEmail: string;
  amount: string;
  currency: Currency;
  provider: string;
  paymentStatus: PaymentStatus;
  outcome: BusinessOutcome;
  risk: RiskLevel;
  lastEvent: string;
  updatedAt: string;
}

export interface TransactionEventRow {
  id: string;
  transactionId: string;
  eventType: string;
  source: string;
  summary: string;
  timestamp: string;
}

export interface TransactionDetail {
  transaction: DemoTransaction;
  events: TransactionEventRow[];
  authorized: string;
  captured: string;
  refunded: string;
  notes: string[];
}

export interface ActiveInvestigation {
  id: string;
  transactionId: string;
  amount: string;
  currency: Currency;
  paymentStatus: PaymentStatus;
  outcome: BusinessOutcome;
  risk: RiskLevel;
  lastEvent: string;
  updatedAt: string;
}

export interface InvestigationCase {
  id: string;
  transactionId: string;
  title: string;
  openedAt: string;
  updatedAt: string;
  priority: "high" | "medium" | "low";
  stage: string;
  owner: string;
  summary: string;
  evidence: string[];
}

export interface FailurePattern {
  id: string;
  name: string;
  description: string;
  transactions: number;
  impact: string;
  trend: "rising" | "stable" | "declining";
  status: "monitoring" | "emerging";
  firstSeen: string;
}

export interface ActivityItem {
  id: string;
  kind: "investigation" | "event" | "pattern" | "outcome" | "refund" | "alert";
  message: string;
  timestamp: string;
  transactionId?: string;
}

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  timestamp: string;
  unread: boolean;
  tone: Tone;
}

export interface ActionQueueItem {
  id: string;
  transactionId: string;
  kind: string;
  priority: RiskLevel;
  status: "queued" | "in_review" | "needs_approval" | "completed";
  assignedTo: string;
  createdAt: string;
}

export interface EventExplorerRow {
  id: string;
  eventType: string;
  transactionId: string;
  source: string;
  summary: string;
  timestamp: string;
}

export interface SimulationPreset {
  id: string;
  name: string;
  description: string;
  availability: string;
}