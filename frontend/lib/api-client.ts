/**
 * Frontend API client for the PAYSCAPE-X backend.
 *
 * All backend calls go through this module so the API base URL and error
 * handling stay in one place. No business logic lives here — only transport.
 */

import type { ApiHealthResponse } from "@/types";
import type {
  ApiAnalysis,
  ApiCompoundFailure,
  ApiConsistencyResult,
  ApiDecision,
  ApiEventStreamResponse,
  ApiEvidenceReport,
  ApiFailureListResponse,
  ApiImpact,
  ApiJourney,
  ApiJourneyGraph,
  ApiJourneyIntegrity,
  ApiOutcome,
  ApiScenarioDetail,
  ApiScenarioSummary,
  ApiSummary,
  ApiSimulationReport,
  ApiSimulationResult,
  ApiTransactionDetail,
  ApiTransactionListResponse,
} from "@/types/api";

/** Base URL of the FastAPI backend. Override with NEXT_PUBLIC_API_BASE_URL. */
export const API_BASE_URL: string = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

/**
 * Per-request timeout. The deterministic backend engines recompute the
 * full pipeline per transaction and take several seconds warm (impact /
 * simulations / decisions routinely run 8-10s; a cold database wake adds
 * more), so a short timeout made transaction details, the Simulation Lab
 * and the failures page fail with "backend unreachable" even when the
 * backend was healthy. 30s keeps real requests working while still
 * failing fast (instead of hanging forever) when the backend is down.
 */
export const API_REQUEST_TIMEOUT_MS = 30_000;

/** Error raised for any failed backend call (timeout, network, HTTP status). */
export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (cause) {
    const aborted =
      cause instanceof DOMException && cause.name === "AbortError";
    throw new ApiError(
      aborted ? "Request timed out" : "Network error — backend unreachable"
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError(`Backend responded with HTTP ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}

/** GET /api/v1/health — liveness + service identity check. */
export function getHealth(): Promise<ApiHealthResponse> {
  return request<ApiHealthResponse>("/api/v1/health");
}

/** Query parameters for GET /api/v1/transactions. */
export interface TransactionsQuery {
  limit?: number;
  offset?: number;
  scenario?: string;
  paymentStatus?: string;
}

/** GET /api/v1/transactions — paginated payment-level journeys. */
export function getTransactions(
  query: TransactionsQuery = {}
): Promise<ApiTransactionListResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.scenario) params.set("scenario", query.scenario);
  if (query.paymentStatus) params.set("payment_status", query.paymentStatus);
  const qs = params.toString();
  return request<ApiTransactionListResponse>(
    `/api/v1/transactions${qs ? `?${qs}` : ""}`
  );
}

/** GET /api/v1/transactions/{id} — full journey: order, payment, events. */
export function getTransaction(id: string): Promise<ApiTransactionDetail> {
  return request<ApiTransactionDetail>(`/api/v1/transactions/${id}`);
}

/** Query parameters for GET /api/v1/events. */
export interface EventsQuery {
  limit?: number;
  offset?: number;
  eventType?: string;
  source?: string;
  correlationId?: string;
}

/** GET /api/v1/events — chronological unified event stream. */
export function getEvents(query: EventsQuery = {}): Promise<ApiEventStreamResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.eventType) params.set("event_type", query.eventType);
  if (query.source) params.set("source", query.source);
  if (query.correlationId) params.set("correlation_id", query.correlationId);
  const qs = params.toString();
  return request<ApiEventStreamResponse>(`/api/v1/events${qs ? `?${qs}` : ""}`);
}

/** GET /api/v1/summary — real dashboard aggregates (deterministic). */
export function getSummary(): Promise<ApiSummary> {
  return request<ApiSummary>("/api/v1/summary");
}

/** GET /api/v1/scenarios — every synthetic scenario with counts. */
export function getScenarios(): Promise<ApiScenarioSummary[]> {
  return request<ApiScenarioSummary[]>("/api/v1/scenarios");
}

/** GET /api/v1/scenarios/{id} — scenario detail with transactions + timeline. */
export function getScenario(id: string): Promise<ApiScenarioDetail> {
  return request<ApiScenarioDetail>(`/api/v1/scenarios/${id}`);
}

/** GET /api/v1/journeys/{id} — reconstructed journey: events + graph + integrity. */
export function getJourney(id: string): Promise<ApiJourney> {
  return request<ApiJourney>(`/api/v1/journeys/${id}`);
}

/** GET /api/v1/journeys/{id}/graph — the deterministic journey graph. */
export function getJourneyGraph(id: string): Promise<ApiJourneyGraph> {
  return request<ApiJourneyGraph>(`/api/v1/journeys/${id}/graph`);
}

/** GET /api/v1/journeys/{id}/integrity — the structural integrity report. */
export function getJourneyIntegrity(id: string): Promise<ApiJourneyIntegrity> {
  return request<ApiJourneyIntegrity>(`/api/v1/journeys/${id}/integrity`);
}

/** GET /api/v1/evidence/{id} — the deterministic evidence report (Part 4). */
export function getEvidence(id: string): Promise<ApiEvidenceReport> {
  return request<ApiEvidenceReport>(`/api/v1/evidence/${id}`);
}

/** GET /api/v1/consistency/{id} — the deterministic consistency report (Part 4). */
export function getConsistency(id: string): Promise<ApiConsistencyResult> {
  return request<ApiConsistencyResult>(`/api/v1/consistency/${id}`);
}

/** GET /api/v1/analysis/{id} — journey + evidence + consistency + outcome. */
export function getAnalysis(id: string): Promise<ApiAnalysis> {
  return request<ApiAnalysis>(`/api/v1/analysis/${id}`);
}

/** GET /api/v1/outcome/{id} — the deterministic business outcome (Part 5). */
export function getOutcome(id: string): Promise<ApiOutcome> {
  return request<ApiOutcome>(`/api/v1/outcome/${id}`);
}

/** GET /api/v1/failures/{id} — the compound-failure analysis (Part 6). */
export function getCompoundFailure(id: string): Promise<ApiCompoundFailure> {
  return request<ApiCompoundFailure>(`/api/v1/failures/${id}`);
}

/** GET /api/v1/impact/{id} — the consequence / impact analysis (Part 6). */
export function getImpact(id: string): Promise<ApiImpact> {
  return request<ApiImpact>(`/api/v1/impact/${id}`);
}

/** GET /api/v1/simulations/{id} — baseline + every intervention result (Part 7). */
export function getSimulations(id: string): Promise<ApiSimulationReport> {
  return request<ApiSimulationReport>(`/api/v1/simulations/${id}`);
}

/** GET /api/v1/simulations/{id}/compare — ranked comparison table (Part 7). */
export function getSimulationCompare(id: string): Promise<ApiSimulationReport> {
  return request<ApiSimulationReport>(`/api/v1/simulations/${id}/compare`);
}

/** POST /api/v1/simulations/{id}/run — run ONE deterministic intervention (Part 7). */
export function runSimulation(
  id: string,
  intervention: string
): Promise<ApiSimulationResult> {
  return request<ApiSimulationResult>(`/api/v1/simulations/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ intervention }),
  });
}

/** GET /api/v1/decisions/{id} — the auditable AI decision (Part 8). */
export function getDecision(id: string): Promise<ApiDecision> {
  return request<ApiDecision>(`/api/v1/decisions/${id}`);
}

/** POST /api/v1/decisions/{decisionId}/approve — record merchant approval (Part 8). */
export function approveDecision(
  decisionId: string,
  note?: string
): Promise<ApiDecision> {
  return request<ApiDecision>(`/api/v1/decisions/${decisionId}/approve`, {
    method: "POST",
    body: JSON.stringify({ note: note ?? null }),
  });
}

/** POST /api/v1/decisions/{decisionId}/reject — record merchant rejection (Part 8). */
export function rejectDecision(
  decisionId: string,
  reason?: string
): Promise<ApiDecision> {
  return request<ApiDecision>(`/api/v1/decisions/${decisionId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

/** Query parameters for GET /api/v1/failures. */
export interface FailuresQuery {
  limit?: number;
  offset?: number;
  severity?: string;
  failureType?: string;
  outcome?: string;
  scope?: string;
}

/** GET /api/v1/failures — detected compound failures across the dataset. */
export function getFailures(
  query: FailuresQuery = {}
): Promise<ApiFailureListResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.severity) params.set("severity", query.severity);
  if (query.failureType) params.set("failure_type", query.failureType);
  if (query.outcome) params.set("outcome", query.outcome);
  if (query.scope) params.set("scope", query.scope);
  const qs = params.toString();
  return request<ApiFailureListResponse>(
    `/api/v1/failures${qs ? `?${qs}` : ""}`
  );
}