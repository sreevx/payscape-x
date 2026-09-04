"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import type { ApiSummary } from "@/types/api";
import { ApiError, getSummary } from "@/lib/api-client";
import { KpiGrid } from "@/components/dashboard/kpi-grid";
import { OutcomeDistribution } from "@/components/dashboard/outcome-distribution";
import { ErrorState, LoadingState } from "@/components/shared/states";
import { Card } from "@/components/ui/card";

type SummaryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; summary: ApiSummary };

/**
 * Fetches the real dashboard aggregates (GET /api/v1/summary) exactly once
 * and renders the KPI grid + outcome distribution from them. Kept as a
 * client island so the dashboard's server render never blocks on the
 * deterministic aggregate scan; loading and error states are honest and
 * never substitute fabricated numbers.
 *
 * `children` is the neighbouring grid cell (Active Investigations) and is
 * rendered regardless of fetch state so the page never goes blank.
 */
export function DashboardSummary({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SummaryState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getSummary()
      .then((summary) => {
        if (!cancelled) setState({ status: "ready", summary });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiError
            ? error.message
            : "The summary API could not be reached.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const loadingCard = (label: string) => (
    <Card size="sm">
      <div className="px-4 pt-3 pb-1 text-xs font-medium text-muted-foreground">
        {label}
      </div>
      <LoadingState rows={3} className="px-4 pb-4" />
    </Card>
  );

  const errorCard = (title: string) => (
    <Card size="sm">
      <ErrorState
        title={title}
        description={`${state.status === "error" ? state.message : ""} Live per-journey outcomes are still on each transaction page.`}
        onRetry={retry}
      />
    </Card>
  );

  return (
    <>
      {state.status === "ready" ? (
        <KpiGrid summary={state.summary} />
      ) : state.status === "loading" ? (
        loadingCard("Dashboard aggregates")
      ) : (
        errorCard("Dashboard aggregates unavailable")
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          {state.status === "ready" ? (
            <OutcomeDistribution summary={state.summary} />
          ) : state.status === "loading" ? (
            loadingCard("Outcome distribution")
          ) : (
            errorCard("Outcome distribution unavailable")
          )}
        </div>
        <div className="lg:col-span-7">{children}</div>
      </div>
    </>
  );
}
