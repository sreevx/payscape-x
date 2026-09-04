import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import SimulationPage from "@/app/simulation/page";

// The Simulation Lab page is client-rendered: it must show a genuine
// loading state while the transaction list is in flight and must NOT
// display a false "Backend unavailable" until the request has actually
// failed.
const { getTransactions, getSimulations, ApiErrorMock } = vi.hoisted(() => {
  class ApiError extends Error {}
  return {
    getTransactions: vi.fn(),
    getSimulations: vi.fn(),
    ApiErrorMock: ApiError,
  };
});

vi.mock("@/lib/api-client", () => ({
  getTransactions: (...args: unknown[]) => getTransactions(...args),
  getSimulations: (...args: unknown[]) => getSimulations(...args),
  ApiError: ApiErrorMock,
}));

beforeEach(() => {
  vi.clearAllMocks();
});

async function flushTimers(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 10));
}

describe("Simulation Lab page loading/error states", () => {
  it("shows a loading state, not 'Backend unavailable', while the list request is in flight", async () => {
    // Never-resolving request: the page is still loading.
    getTransactions.mockReturnValue(new Promise(() => {}));
    render(<SimulationPage />);
    await flushTimers();
    expect(screen.getByText(/Loading the transaction list/)).toBeInTheDocument();
    expect(screen.queryByText(/Backend unavailable/)).not.toBeInTheDocument();
  });

  it("shows 'Backend unavailable' only after the request has failed", async () => {
    getTransactions.mockRejectedValue(
      new ApiErrorMock("The transactions API could not be reached.")
    );
    render(<SimulationPage />);
    await flushTimers();
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  });
});
