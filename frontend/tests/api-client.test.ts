import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  API_BASE_URL,
  approveDecision,
  getCompoundFailure,
  getConsistency,
  getDecisions,
  getDecision,
  getEvents,
  getEvidence,
  getFailures,
  getHealth,
  getImpact,
  getJourney,
  getJourneyGraph,
  getJourneyIntegrity,
  getOutcome,
  getSimulationCompare,
  getSimulations,
  getSummary,
  getTransactions,
  rejectDecision,
  runSimulation,
} from "@/lib/api-client";

const HEALTH_URL = `${API_BASE_URL}/api/v1/health`;

function mockFetchResponse(body: unknown, ok: boolean, status: number): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status,
      json: async () => body,
    })
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getHealth", () => {
  it("calls GET /api/v1/health and returns the parsed payload", async () => {
    const body = {
      status: "ok",
      service: "payscape-x",
      version: "0.1.0",
      database: "unavailable",
    };
    mockFetchResponse(body, true, 200);

    await expect(getHealth()).resolves.toEqual(body);

    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(HEALTH_URL);
    expect(init).toMatchObject({ signal: expect.any(AbortSignal) });
  });

  it("rejects with ApiError when the backend responds with a non-2xx status", async () => {
    mockFetchResponse({ detail: "boom" }, false, 503);

    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
    await expect(getHealth()).rejects.toMatchObject({
      status: 503,
    });
  });

  it("rejects with ApiError when the backend is unreachable (network failure)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
    await expect(getHealth()).rejects.toMatchObject({
      status: null,
    });
  });
});

describe("getTransactions", () => {
  it("calls GET /api/v1/transactions with query params", async () => {
    const body = {
      items: [
        {
          id: "tx-1",
          order_id: "ord-1",
          external_order_id: "ORD-2026-1001",
          customer_name: "Anika Gupta",
          customer_email: "a@example.in",
          amount: "2499.0000",
          currency: "INR",
          payment_status: "CAPTURED",
          provider: "razorpay",
          method: "UPI",
          scenario_type: "NORMAL_SUCCESS",
          scenario_slug: "normal_success",
          event_count: 17,
          created_at: "2026-09-03T10:21:56",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    };
    mockFetchResponse(body, true, 200);

    await expect(
      getTransactions({ limit: 50, scenario: "normal_success" })
    ).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(
      `${API_BASE_URL}/api/v1/transactions?limit=50&scenario=normal_success`
    );
  });

  it("rejects with ApiError on a 503", async () => {
    mockFetchResponse({ detail: "db unavailable" }, false, 503);
    await expect(getTransactions()).rejects.toMatchObject({ status: 503 });
  });
});

describe("getJourney / getJourneyGraph / getJourneyIntegrity", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";

  it("calls GET /api/v1/journeys/{id}", async () => {
    const body = {
      transaction_id: id,
      order_id: "ord-1",
      payment_id: id,
      correlation_id: "corr-1",
      events: [],
      graph: { transaction_id: id, correlation_id: "corr-1", layout: "deterministic_linear", nodes: [], edges: [] },
      integrity: {
        transaction_id: id,
        total_events: 0,
        linked_events: 0,
        orphan_count: 0,
        duplicate_count: 0,
        unknown_count: 0,
        delayed_count: 0,
        out_of_order_count: 0,
        first_event_at: null,
        last_event_at: null,
        duration_seconds: null,
        missing_expected_event_candidates: [],
        contradictions: [],
        duplicates: [],
        out_of_order_events: [],
        delayed_events: [],
        unknown_events: [],
        orphan_events: [],
      },
    };
    mockFetchResponse(body, true, 200);

    await expect(getJourney(id)).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/journeys/${id}`);
  });

  it("calls GET /api/v1/journeys/{id}/graph", async () => {
    const body = {
      transaction_id: id,
      correlation_id: "corr-1",
      layout: "deterministic_linear",
      nodes: [{ id: "n-1", kind: "event", label: "ORDER_CREATED", position: { x: 0, y: 112 } }],
      edges: [],
    };
    mockFetchResponse(body, true, 200);

    await expect(getJourneyGraph(id)).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/journeys/${id}/graph`);
  });

  it("calls GET /api/v1/journeys/{id}/integrity and rejects on 404", async () => {
    const body = {
      transaction_id: id,
      total_events: 17,
      linked_events: 17,
      orphan_count: 0,
      duplicate_count: 0,
      unknown_count: 0,
      delayed_count: 0,
      out_of_order_count: 0,
      first_event_at: "2026-08-24T00:00:00",
      last_event_at: "2026-08-24T01:25:00",
      duration_seconds: 5100,
      missing_expected_event_candidates: [],
      contradictions: [],
      duplicates: [],
      out_of_order_events: [],
      delayed_events: [],
      unknown_events: [],
      orphan_events: [],
    };
    mockFetchResponse(body, true, 200);
    await expect(getJourneyIntegrity(id)).resolves.toEqual(body);

    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getJourneyIntegrity(id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("getEvidence / getConsistency", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";

  it("calls GET /api/v1/evidence/{id}", async () => {
    const body = {
      transaction_id: id,
      evidence: [
        {
          evidence_id: "ev-1",
          category: "PAYMENT_EVIDENCE",
          claim: "Payment was captured",
          event_ids: ["evt-1"],
          source: "TRANSACTION_EVENT",
          timestamp: "2026-08-24T00:08:00",
          supporting_data: { events: [{ event_id: "evt-1" }] },
          strength: "CORROBORATED",
          rule_id: "PAYMENT_CAPTURED_PRESENT",
          confidence: 1.0,
          contradictions: [],
          metadata: {},
        },
      ],
      gaps: [],
      contradictions: [],
      strength_summary: { DIRECT: 1, CORROBORATED: 1, INDIRECT: 0, MISSING: 0, CONTRADICTED: 0 },
    };
    mockFetchResponse(body, true, 200);

    await expect(getEvidence(id)).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/evidence/${id}`);
  });

  it("calls GET /api/v1/consistency/{id} and surfaces the overall integrity", async () => {
    const body = {
      transaction_id: id,
      checks: [
        {
          rule_id: "PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED",
          name: "Payment capture requires payment creation",
          description: "PAYMENT_CAPTURED must be backed by a PAYMENT_CREATED record.",
          severity: "MEDIUM",
          status: "PASS",
          supporting_event_ids: ["evt-1", "evt-2"],
          explanation: "payment capture is preceded by a payment creation record",
        },
      ],
      passed: ["PAYMENT_CAPTURE_REQUIRES_PAYMENT_CREATED"],
      violations: [],
      insufficient_evidence: [],
      not_applicable: [],
      overall_integrity: "CONSISTENT",
    };
    mockFetchResponse(body, true, 200);

    const result = await getConsistency(id);
    expect(result.overall_integrity).toBe("CONSISTENT");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/consistency/${id}`);
  });

  it("rejects with ApiError on a 404 from either endpoint", async () => {
    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getEvidence(id)).rejects.toMatchObject({ status: 404 });
    await expect(getConsistency(id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("getSummary", () => {
  it("calls GET /api/v1/summary and returns the parsed payload", async () => {
    const body = {
      total_transactions: 150,
      payment_success_count: 130,
      payment_failed_count: 20,
      payment_pending_count: 0,
      payment_success_rate: 86.7,
      payment_failed_rate: 13.3,
      outcomes: { fulfilled: 90, at_risk: 0, failed: 50, unverifiable: 10 },
      fulfilled_rate: 60.0,
      at_risk_rate: 0.0,
      failed_rate: 33.3,
      unverifiable_rate: 6.7,
      source: "Deterministic outcome engine (Part 5)",
      computed_at: "2026-09-04T00:00:00Z",
    };
    mockFetchResponse(body, true, 200);

    await expect(getSummary()).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/summary`);
  });

  it("rejects with ApiError when the summary responds with a non-2xx", async () => {
    mockFetchResponse({ detail: "boom" }, false, 503);
    await expect(getSummary()).rejects.toMatchObject({ status: 503 });
  });
});

describe("getOutcome", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";

  it("calls GET /api/v1/outcome/{id}", async () => {
    const body = {
      transaction_id: id,
      outcome: "FAILED",
      confidence: 0.9,
      primary_reason: {
        code: "ORDER_NOT_CONFIRMED",
        message: "Confirmation SLA expired — the order was never confirmed.",
        severity: "HIGH",
        rule_id: "BUSINESS_FAILURE_MARKERS",
        event_ids: ["evt-1"],
        evidence_ids: ["ev-1"],
      },
      reasons: [],
      supporting_evidence_ids: ["ev-1"],
      supporting_event_ids: ["evt-1"],
      blocking_evidence_ids: [],
      consistency_status: "CONSISTENT",
      evidence_completeness: 0.6,
      rule_trace: [
        { rule_id: "CRITICAL_CONTRADICTION", name: "x", priority: 10, outcome: "UNVERIFIABLE", applied: false, note: "not applied" },
      ],
      confidence_adjustments: [],
    };
    mockFetchResponse(body, true, 200);

    const result = await getOutcome(id);
    expect(result.outcome).toBe("FAILED");
    expect(result.primary_reason.code).toBe("ORDER_NOT_CONFIRMED");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/outcome/${id}`);
  });

  it("rejects with ApiError on a 404", async () => {
    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getOutcome(id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("getCompoundFailure / getImpact / getFailures", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";

  it("calls GET /api/v1/failures/{id}", async () => {
    const body = {
      compound_failure_id: "cf-1",
      transaction_id: id,
      detected: true,
      reason: "MULTI_STAGE_FAILURE_CHAIN",
      severity: "CRITICAL",
      classification: "OBSERVED",
      primary_failure: { node_id: "n-1", kind: "INVENTORY_ALLOCATION_FAILED", stage: "INVENTORY", label: "Inventory allocation failed", status: "OBSERVED", message: "m", rule_id: "r", event_ids: [], evidence_ids: [], timestamp: null, metadata: {} },
      failure_chain: [],
      edges: [],
      root_causes: [],
      confidence: 0.95,
      event_ids: [],
      evidence_ids: [],
      metadata: {},
    };
    mockFetchResponse(body, true, 200);

    const result = await getCompoundFailure(id);
    expect(result.detected).toBe(true);
    expect(result.primary_failure?.kind).toBe("INVENTORY_ALLOCATION_FAILED");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/failures/${id}`);
  });

  it("calls GET /api/v1/impact/{id}", async () => {
    const body = {
      impact_id: "im-1",
      transaction_id: id,
      scope: "MULTI_TRANSACTION",
      affected_transactions: 3,
      affected_orders: 3,
      affected_products: 1,
      observed_consequences: [],
      derived_consequences: [],
      potential_consequences: [],
      severity: "CRITICAL",
      impact_score: 88.0,
      shared_skus: ["NC-0006"],
      shared_failure_patterns: ["INVENTORY_OUT_OF_STOCK"],
      affected: [],
      score_components: [],
      event_ids: [],
      evidence_ids: [],
      metadata: {},
    };
    mockFetchResponse(body, true, 200);

    const result = await getImpact(id);
    expect(result.scope).toBe("MULTI_TRANSACTION");
    expect(result.impact_score).toBe(88.0);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/impact/${id}`);
  });

  it("calls GET /api/v1/failures with filters and parses the list", async () => {
    const body = {
      items: [
        {
          transaction_id: id,
          order_id: "ord-1",
          external_order_id: "ORD-2026-1146",
          scenario_type: "COMPOUND_FAILURE",
          scenario_slug: "compound_failure",
          outcome: "FAILED",
          severity: "CRITICAL",
          classification: "OBSERVED",
          detected: true,
          primary_failure_kind: "INVENTORY_ALLOCATION_FAILED",
          primary_failure_label: "Inventory allocation failed",
          root_cause_kinds: ["INVENTORY_ALLOCATION_FAILED"],
          chain_length: 6,
          distinct_stages: ["CUSTOMER", "FULFILLMENT", "INVENTORY"],
          confidence: 0.95,
          scope: "MULTI_TRANSACTION",
          affected_transactions: 4,
          shared_skus: ["NC-0013"],
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    };
    mockFetchResponse(body, true, 200);

    const result = await getFailures({ limit: 20, severity: "CRITICAL" });
    expect(result.total).toBe(1);
    expect(result.items[0].primary_failure_kind).toBe("INVENTORY_ALLOCATION_FAILED");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(
      `${API_BASE_URL}/api/v1/failures?limit=20&severity=CRITICAL`
    );
  });

  it("rejects with ApiError on a 404 from either detail endpoint", async () => {
    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getCompoundFailure(id)).rejects.toMatchObject({ status: 404 });
    await expect(getImpact(id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("getSimulations / runSimulation / getSimulationCompare", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";

  const reportBody = {
    transaction_id: id,
    baseline: {
      transaction_id: id,
      outcome: "FAILED",
      confidence: 0.95,
      consistency_status: "CONSISTENT",
      compound_failure_detected: true,
      severity: "CRITICAL",
      impact_score: 100.0,
      impact_scope: "MULTI_TRANSACTION",
      affected_transactions: 3,
      root_causes: [
        { kind: "INVENTORY_ALLOCATION_FAILED", label: "Inventory allocation failed", rule_id: "NODE_OBSERVED_INVENTORY_ALLOCATION_FAILED" },
      ],
      event_ids: ["evt-1"],
      evidence_ids: ["ev-1"],
    },
    interventions: [
      {
        simulation_id: "sim-1",
        transaction_id: id,
        status: "SIMULATED",
        reason: "No intervention is applied.",
        intervention: { intervention_type: "DO_NOTHING", label: "Do Nothing", description: "Take no action." },
        baseline_outcome: "FAILED",
        baseline_confidence: 0.95,
        simulated_outcome: "FAILED",
        simulated_confidence: 0.95,
        baseline_impact_score: 100.0,
        simulated_impact_score: 100.0,
        delta_impact_score: 0.0,
        resolved_failures: [],
        remaining_failures: [],
        new_risks: [],
        assumptions: ["The simulated world is identical to the observed records."],
        event_ids: [],
        evidence_ids: [],
        rule_ids: ["SIM_DO_NOTHING"],
        metadata: { simulated: true },
      },
    ],
    comparison: [
      {
        rank: 1,
        intervention_type: "DO_NOTHING",
        label: "Do Nothing",
        status: "SIMULATED",
        simulated_outcome: "FAILED",
        simulated_impact_score: 100.0,
        delta_impact_score: 0.0,
        remaining_failure_count: 0,
        assumption_count: 1,
      },
    ],
  };

  it("calls GET /api/v1/simulations/{id}", async () => {
    mockFetchResponse(reportBody, true, 200);

    const report = await getSimulations(id);
    expect(report.baseline.outcome).toBe("FAILED");
    expect(report.interventions[0].status).toBe("SIMULATED");
    expect(report.comparison[0].intervention_type).toBe("DO_NOTHING");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/simulations/${id}`);
  });

  it("calls GET /api/v1/simulations/{id}/compare", async () => {
    mockFetchResponse(reportBody, true, 200);

    const report = await getSimulationCompare(id);
    expect(report.comparison[0].rank).toBe(1);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/simulations/${id}/compare`);
  });

  it("calls POST /api/v1/simulations/{id}/run with an intervention body", async () => {
    mockFetchResponse(reportBody.interventions[0], true, 200);

    const result = await runSimulation(id, "ALTERNATIVE_INVENTORY");
    expect(result.intervention.intervention_type).toBe("DO_NOTHING");

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/simulations/${id}/run`);
    expect(init).toMatchObject({ method: "POST" });
    expect((init?.body as string | undefined) ?? "").toBe(
      JSON.stringify({ intervention: "ALTERNATIVE_INVENTORY" })
    );
  });

  it("rejects with ApiError on a 404 / 400 from the lab endpoints", async () => {
    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getSimulations(id)).rejects.toMatchObject({ status: 404 });
    await expect(getSimulationCompare(id)).rejects.toMatchObject({ status: 404 });
    await expect(runSimulation(id, "NOPE")).rejects.toMatchObject({ status: 404 });
  });
});

describe("getDecision / approveDecision / rejectDecision", () => {
  const id = "4f6c0f5a-1111-2222-3333-444444444444";
  const decisionId = "7b8c9d0e-1111-2222-3333-444444444444";

  const decisionBody = {
    decision_id: decisionId,
    transaction_id: id,
    decision_source: "DETERMINISTIC_FALLBACK",
    recommended_action: "REFUND_OR_CONTAIN",
    reason: "A customer-impacting failure is recorded and the refund simulation is applicable.",
    decision_confidence: 0.967,
    evidence_confidence: 1.0,
    evidence_ids: ["ev-1", "ev-2"],
    event_ids: ["evt-1"],
    simulation_id: "sim-1",
    alternatives: [
      { action: "DO_NOTHING", reason: "Take no action." },
      { action: "HUMAN_REVIEW", reason: "Escalate to humans." },
    ],
    human_approval_required: true,
    approval_status: "PENDING",
    rejection_reason: null,
    decided_at: null,
    created_at: "2026-09-03T10:00:00",
    updated_at: "2026-09-03T10:00:00",
    metadata: { fallback_rule_id: "DEC_CUSTOMER_IMPACT_CONTAIN" },
  };

  it("calls GET /api/v1/decisions/{id}", async () => {
    mockFetchResponse(decisionBody, true, 200);

    const decision = await getDecision(id);
    expect(decision.recommended_action).toBe("REFUND_OR_CONTAIN");
    expect(decision.approval_status).toBe("PENDING");

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/decisions/${id}`);
  });

  it("calls POST /api/v1/decisions/{decisionId}/approve", async () => {
    mockFetchResponse({ ...decisionBody, approval_status: "APPROVED" }, true, 200);

    const decision = await approveDecision(decisionId, "merchant reviewed");
    expect(decision.approval_status).toBe("APPROVED");

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/decisions/${decisionId}/approve`);
    expect(init).toMatchObject({ method: "POST" });
    expect((init?.body as string | undefined) ?? "").toBe(
      JSON.stringify({ note: "merchant reviewed" })
    );
  });

  it("calls POST /api/v1/decisions/{decisionId}/reject with a reason", async () => {
    mockFetchResponse(
      { ...decisionBody, approval_status: "REJECTED", rejection_reason: "no" },
      true,
      200
    );

    const decision = await rejectDecision(decisionId, "no");
    expect(decision.approval_status).toBe("REJECTED");
    expect(decision.rejection_reason).toBe("no");

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/decisions/${decisionId}/reject`);
    expect((init?.body as string | undefined) ?? "").toBe(
      JSON.stringify({ reason: "no" })
    );
  });

  it("rejects with ApiError on 404 / 409 from the decision endpoints", async () => {
    mockFetchResponse({ detail: "Transaction not found" }, false, 404);
    await expect(getDecision(id)).rejects.toMatchObject({ status: 404 });
    mockFetchResponse({ detail: "Decision is already APPROVED" }, false, 409);
    await expect(approveDecision(decisionId)).rejects.toMatchObject({ status: 409 });
    await expect(rejectDecision(decisionId, "x")).rejects.toMatchObject({ status: 409 });
  });
});

describe("getDecisions", () => {
  it("calls GET /api/v1/decisions and returns the recorded queue", async () => {
    const body = {
      items: [
        {
          decision_id: "dec-1",
          transaction_id: "tx-1",
          external_order_id: "ORD-2026-1145",
          amount: "4545.00",
          currency: "INR",
          payment_status: "CAPTURED",
          outcome: "FAILED",
          decision_source: "DETERMINISTIC_FALLBACK",
          recommended_action: "REFUND_OR_CONTAIN",
          reason: "Customer impact recorded after a successful capture.",
          decision_confidence: 0.9,
          evidence_confidence: 0.95,
          approval_status: "PENDING",
          human_approval_required: true,
          created_at: "2026-09-04T10:43:26",
          updated_at: "2026-09-04T10:43:26",
        },
      ],
      total: 1,
    };
    mockFetchResponse(body, true, 200);

    await expect(getDecisions()).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/v1/decisions`);
  });
});

describe("getEvents", () => {
  it("calls GET /api/v1/events with type/source/correlation filters", async () => {
    const body = {
      items: [
        {
          id: "evt-1",
          order_id: "ord-1",
          external_order_id: "ORD-2026-1001",
          payment_id: "pay-1",
          event_type: "PAYMENT_CAPTURED",
          source: "PAYMENT_PROVIDER",
          timestamp: "2026-09-03T10:21:56",
          correlation_id: "corr-1",
          idempotency_key: "capture:evt_x",
          payload: { amount: "2499.0000" },
        },
      ],
      total: 135,
      limit: 50,
      offset: 0,
    };
    mockFetchResponse(body, true, 200);

    await expect(
      getEvents({ eventType: "PAYMENT_CAPTURED", source: "PAYMENT_PROVIDER" })
    ).resolves.toEqual(body);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(
      `${API_BASE_URL}/api/v1/events?event_type=PAYMENT_CAPTURED&source=PAYMENT_PROVIDER`
    );
  });
});