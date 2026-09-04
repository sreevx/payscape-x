import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { DashboardSummary } from "@/components/dashboard/dashboard-summary";

// The dashboard summary is client-rendered from GET /api/v1/summary: it
// must show the REAL deterministic aggregates and never fall back to the
// old fabricated sample numbers (98.4% / 94.1% / 2.2%).
const { getSummary, ApiErrorMock } = vi.hoisted(() => {
  class ApiError extends Error {}
  return { getSummary: vi.fn(), ApiErrorMock: ApiError };
});

vi.mock("@/lib/api-client", () => ({
  getSummary: (...args: unknown[]) => getSummary(...args),
  ApiError: ApiErrorMock,
}));

const REAL_SUMMARY = {
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

beforeEach(() => {
  vi.clearAllMocks();
});

async function flushTimers(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 10));
}

describe("Dashboard summary aggregates", () => {
  it("renders the real aggregates and no fabricated sample numbers", async () => {
    getSummary.mockResolvedValue(REAL_SUMMARY);
    render(
      <DashboardSummary>
        <div>neighbour slot</div>
      </DashboardSummary>
    );

    expect(await screen.findByText("86.7%")).toBeInTheDocument();
    // Some rates appear on both a KPI card and the distribution legend.
    expect(screen.getAllByText("60.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("33.3%").length).toBeGreaterThan(0);
    expect(screen.getByText("6.7%")).toBeInTheDocument();
    expect(screen.getAllByText("0.0%").length).toBeGreaterThan(0);
    // The fabricated sample values must be gone.
    expect(screen.queryByText("98.4%")).not.toBeInTheDocument();
    expect(screen.queryByText("94.1%")).not.toBeInTheDocument();
    expect(screen.queryByText("2.2%")).not.toBeInTheDocument();
    expect(screen.queryByText("DEMO DATA")).not.toBeInTheDocument();
    // Neighbour cell renders regardless of fetch state.
    expect(screen.getByText("neighbour slot")).toBeInTheDocument();
  });

  it("shows an honest error with retry when the summary request fails", async () => {
    getSummary.mockRejectedValue(new ApiErrorMock("Request timed out"));
    render(
      <DashboardSummary>
        <div>neighbour slot</div>
      </DashboardSummary>
    );
    expect(
      await screen.findByText("Dashboard aggregates unavailable")
    ).toBeInTheDocument();
    // Both the KPI area and the distribution area expose a retry action.
    expect(screen.getAllByRole("button", { name: /retry/i }).length).toBeGreaterThan(0);
    // Renders without cleanup between tests in this file; tolerate repeats.
    expect(screen.getAllByText("neighbour slot").length).toBeGreaterThan(0);
  });

  it("renders a loading state (never fabricated numbers) while in flight", async () => {
    getSummary.mockReturnValue(new Promise(() => {}));
    render(<DashboardSummary>{null}</DashboardSummary>);
    await flushTimers();
    expect(screen.getByText("Dashboard aggregates")).toBeInTheDocument();
    expect(screen.queryByText("98.4%")).not.toBeInTheDocument();
    expect(screen.queryByText("94.1%")).not.toBeInTheDocument();
  });
});
