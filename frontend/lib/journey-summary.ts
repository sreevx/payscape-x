/**
 * Plain-English journey summaries for the transaction detail page (Part 10).
 *
 * These helpers turn raw event types / engine outputs into the short
 * human-readable narrative a first-time user needs BEFORE any technical
 * terminology: "Payment captured", "Order not confirmed", "Delivered".
 *
 * Everything here is a deterministic label derived from the recorded event
 * stream — it never fabricates a state and never makes a judgement the
 * engines did not make.
 */

import type { ApiBusinessOutcome, ApiEventItem, ApiPaymentStatus } from "@/types/api";
import type { Tone } from "@/types/demo";

export interface JourneyMilestone {
  key: string;
  label: string;
  /** reached = a positive record exists, blocked = an explicit failure
   *  record exists, pending = nothing recorded (never a verdict). */
  state: "reached" | "blocked" | "pending";
  tone: Tone;
  note: string;
}

const has = (events: ApiEventItem[], type: string) =>
  events.some((event) => event.event_type === type);

/**
 * The six business milestones of a journey, derived deterministically from
 * the unified event stream. Order and labels are the business story; the
 * technical event names stay in the advanced details below.
 */
export function journeyMilestones(events: ApiEventItem[]): JourneyMilestone[] {
  const milestones: JourneyMilestone[] = [];

  if (has(events, "PAYMENT_FAILED")) {
    milestones.push({
      key: "payment",
      label: "Payment declined",
      state: "blocked",
      tone: "danger",
      note: "The payment attempt failed — no money moved.",
    });
  } else if (has(events, "PAYMENT_CAPTURED")) {
    milestones.push({
      key: "payment",
      label: "Payment captured",
      state: "reached",
      tone: "success",
      note: "The customer paid successfully.",
    });
  } else {
    milestones.push({
      key: "payment",
      label: "Payment created",
      state: "pending",
      tone: "neutral",
      note: "No capture or failure recorded.",
    });
  }

  if (has(events, "ORDER_CONFIRMED")) {
    milestones.push({
      key: "order",
      label: "Order confirmed",
      state: "reached",
      tone: "success",
      note: "The merchant accepted the order.",
    });
  } else if (has(events, "ORDER_NOT_CONFIRMED")) {
    milestones.push({
      key: "order",
      label: "Order not confirmed",
      state: "blocked",
      tone: "danger",
      note: "The confirmation window expired.",
    });
  } else if (has(events, "ORDER_CANCELLED")) {
    milestones.push({
      key: "order",
      label: "Order cancelled",
      state: "blocked",
      tone: "danger",
      note: "The order was cancelled.",
    });
  } else {
    milestones.push({
      key: "order",
      label: "Order confirmation",
      state: "pending",
      tone: "neutral",
      note: "No confirmation recorded.",
    });
  }

  if (has(events, "INVENTORY_OUT_OF_STOCK")) {
    milestones.push({
      key: "inventory",
      label: "Out of stock",
      state: "blocked",
      tone: "danger",
      note: "Stock could not be allocated.",
    });
  } else if (has(events, "INVENTORY_RESERVED")) {
    milestones.push({
      key: "inventory",
      label: "Stock reserved",
      state: "reached",
      tone: "success",
      note: "Inventory was allocated.",
    });
  } else {
    milestones.push({
      key: "inventory",
      label: "Inventory",
      state: "pending",
      tone: "neutral",
      note: "No allocation recorded.",
    });
  }

  if (has(events, "FULFILLMENT_SHIPPED")) {
    milestones.push({
      key: "fulfillment",
      label: "Fulfilled & shipped",
      state: "reached",
      tone: "success",
      note: "The order was picked, packed and shipped.",
    });
  } else if (has(events, "NO_FULFILLMENT") || has(events, "FULFILLMENT_FAILED")) {
    milestones.push({
      key: "fulfillment",
      label: "Not fulfilled",
      state: "blocked",
      tone: "danger",
      note: "No fulfillment was created.",
    });
  } else if (has(events, "FULFILLMENT_CREATED")) {
    milestones.push({
      key: "fulfillment",
      label: "Fulfillment started",
      state: "pending",
      tone: "info",
      note: "Fulfillment exists but was not shipped.",
    });
  } else {
    milestones.push({
      key: "fulfillment",
      label: "Fulfillment",
      state: "pending",
      tone: "neutral",
      note: "No fulfillment recorded.",
    });
  }

  if (has(events, "DELIVERY_COMPLETED")) {
    milestones.push({
      key: "delivery",
      label: "Delivered",
      state: "reached",
      tone: "success",
      note: "The customer received the order.",
    });
  } else if (has(events, "DELIVERY_FAILED")) {
    milestones.push({
      key: "delivery",
      label: "Delivery failed",
      state: "blocked",
      tone: "danger",
      note: "The delivery could not be completed.",
    });
  } else if (has(events, "DELIVERY_RETURNED")) {
    milestones.push({
      key: "delivery",
      label: "Returned",
      state: "blocked",
      tone: "danger",
      note: "The order was returned.",
    });
  } else {
    milestones.push({
      key: "delivery",
      label: "Delivery",
      state: "pending",
      tone: "neutral",
      note: "No delivery resolution recorded.",
    });
  }

  if (has(events, "REFUND_COMPLETED")) {
    milestones.push({
      key: "refund",
      label: "Refund completed",
      state: "reached",
      tone: "info",
      note: "The captured amount was returned.",
    });
  } else if (has(events, "REFUND_INITIATED")) {
    milestones.push({
      key: "refund",
      label: "Refund initiated",
      state: "reached",
      tone: "info",
      note: "A refund was started.",
    });
  }

  return milestones;
}

/** Display form of an outcome for the hero ("AT RISK", not "AT_RISK"). */
export function displayOutcome(outcome: ApiBusinessOutcome): string {
  switch (outcome) {
    case "AT_RISK":
      return "AT RISK";
    default:
      return outcome;
  }
}

/**
 * One plain-English headline for the transaction, derived only from the
 * payment status and the deterministic Part 5 outcome. This is the first
 * sentence a first-time user reads.
 */
export function outcomeHeadline(
  paymentStatus: ApiPaymentStatus,
  outcome: ApiBusinessOutcome
): string {
  switch (outcome) {
    case "FULFILLED":
      return "Payment succeeded and the order was delivered.";
    case "AT_RISK":
      return "Payment succeeded, but an unresolved problem threatens completion.";
    case "FAILED":
      return paymentStatus === "FAILED"
        ? "The payment was declined, so the order could not proceed."
        : "Payment succeeded, but the business transaction did not complete.";
    case "UNVERIFIABLE":
      return "The records are insufficient or contradictory — the business outcome cannot be verified.";
  }
}