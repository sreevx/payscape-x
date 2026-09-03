/**
 * Shared domain types for PAYSCAPE-X.
 *
 * These mirror the backend entities (backend/app/models) so the frontend
 * and backend speak the same vocabulary. Keep them aligned with the API
 * schemas when API endpoints are added in later parts.
 */

/** Universal identifier (UUID strings from the backend). */
export type ID = string;

export type Currency = "INR" | "USD" | "EUR" | "GBP";

export type OrderStatus =
  | "created"
  | "authorized"
  | "paid"
  | "fulfilled"
  | "cancelled"
  | "refunded";

export type PaymentStatus =
  | "succeeded"
  | "failed"
  | "pending"
  | "refunded"
  | "disputed";

export interface Merchant {
  id: ID;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface Customer {
  id: ID;
  externalId: string;
  name: string;
  email: string;
  createdAt: string;
}

export interface Order {
  id: ID;
  merchantId: ID;
  customerId: ID;
  externalOrderId: string;
  amount: string;
  currency: Currency;
  status: OrderStatus;
  createdAt: string;
  updatedAt: string;
}

export interface Payment {
  id: ID;
  orderId: ID;
  provider: string;
  providerPaymentId: string;
  amount: string;
  currency: Currency;
  status: PaymentStatus;
  createdAt: string;
  updatedAt: string;
}

/** Structured event types — every future module must consume these. */
export type TransactionEventType =
  | "payment.succeeded"
  | "payment.failed"
  | "payment.pending"
  | "payment.refunded"
  | "payment.disputed"
  | "order.created"
  | "order.fulfilled"
  | "order.cancelled"
  | "inventory.allocated"
  | "inventory.out_of_stock"
  | "fulfillment.shipped"
  | "delivery.in_transit"
  | "delivery.delivered"
  | "delivery.failed";

export interface TransactionEvent {
  id: ID;
  transactionId: ID;
  eventType: TransactionEventType;
  source: string;
  timestamp: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

/** Response contract for `GET /api/v1/health`. */
export interface ApiHealthResponse {
  status: "ok";
  service: string;
  version: string;
  database: "ok" | "unavailable";
}