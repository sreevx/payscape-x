"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

import {
  ApiError,
  getSimulations,
  getTransactions,
} from "@/lib/api-client";
import type { ApiSimulationReport, ApiTransactionListItem } from "@/types/api";
import { SimulationPanel } from "@/components/simulation/simulation-panel";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/status-badge";
import { ErrorState } from "@/components/shared/states";

/**
 * Simulation Lab page (Part 7).
 *
 * Replaces the Part 1 placeholder presets with the real, deterministic
 * simulation engine: pick a seeded transaction and compare every
 * intervention (do nothing, retry fulfillment, alternative inventory,
 * substitute product, refund, human review) against its ACTUAL baseline.
 * Every result is labelled SIMULATED — the lab never recommends and never
 * guarantees.
 */

const SCENARIO_LABELS: Record<string, string> = {
  normal_success: "Normal Success",
  payment_failed: "Payment Failed",
  duplicate_webhook: "Duplicate Webhook",
  delayed_webhook: "Delayed Webhook",
  inventory_failure: "Inventory Failure",
  delivery_failure: "Delivery Failure",
  refund_flow: "Refund Flow",
  missing_event: "Missing Event",
  contradictory_event: "Contradictory Event",
  compound_failure: "Compound Failure",
};

function scenarioLabel(slug: string | null): string {
  if (!slug) return "—";
  return SCENARIO_LABELS[slug] ?? slug.replaceAll("_", " ").toUpperCase();
}

function txLabel(tx: ApiTransactionListItem): string {
  return `${scenarioLabel(tx.scenario_slug)} · ${tx.external_order_id} · ${tx.id.slice(0, 8)}`;
}

export default function SimulationPage() {
  const [transactions, setTransactions] = useState<ApiTransactionListItem[] | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [report, setReport] = useState<ApiSimulationReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const loadReport = useCallback(async (transactionId: string) => {
    try {
      const next = await getSimulations(transactionId);
      setReport(next);
      setReportError(null);
    } catch (error) {
      setReport(null);
      setReportError(
        error instanceof ApiError
          ? `The simulations API could not be reached (HTTP ${error.status ?? "network"}).`
          : "The simulations API could not be reached."
      );
    }
  }, []);

  // Initial load: fetch the transaction list and pre-select the Compound
  // Failure case (the primary PAYSCAPE-X demonstration journey).
  useEffect(() => {
    let cancelled = false;
    getTransactions({ limit: 200 })
      .then(async (body) => {
        if (cancelled) return;
        setTransactions(body.items);
        const defaultTx =
          body.items.find((item) => item.scenario_slug === "compound_failure") ??
          body.items[0];
        if (defaultTx) {
          setSelectedId(defaultTx.id);
          await loadReport(defaultTx.id);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setListError(
            error instanceof ApiError
              ? `The transactions API could not be reached (HTTP ${error.status ?? "network"}).`
              : "The transactions API could not be reached."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadReport]);

  const handleSelect = (transactionId: string) => {
    setSelectedId(transactionId);
    void loadReport(transactionId);
  };

  const grouped = useMemo(() => {
    if (!transactions) return [];
    const groups = new Map<string, ApiTransactionListItem[]>();
    for (const tx of transactions) {
      const key = tx.scenario_slug ?? "other";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(tx);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [transactions]);

  if (listError) {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <PageHeader
          title="Simulation Lab"
          subtitle="Compare possible interventions against already-analyzed transactions."
        />
        <Card size="sm">
          <ErrorState
            title="Backend unavailable"
            description={listError}
          />
        </Card>
      </div>
    );
  }

  if (transactions === null) {
    // First paint before the transaction list resolves: show a loading
    // state — never a false "Backend unavailable" while the request is
    // still in flight.
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <PageHeader
          title="Simulation Lab"
          subtitle="Compare possible interventions against already-analyzed transactions."
        />
        <Card size="sm">
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Loading the transaction list…
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const currentReport = report && report.transaction_id === selectedId ? report : null;
  const loading = selectedId !== "" && !currentReport && !reportError;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Simulation Lab"
        subtitle="Deterministic, read-only counterfactuals over the analyzed journeys — every result is SIMULATED, never a prediction or guarantee."
        actions={
          <StatusBadge tone="warning">
            {transactions.length} TRANSACTIONS ANALYZABLE
          </StatusBadge>
        }
      />

      {/* Transaction picker */}
      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Transaction</CardTitle>
          <CardDescription className="text-xs">
            Choose a seeded transaction to compare its interventions. The
            Compound Failure scenario is pre-selected — the primary PAYSCAPE-X
            demonstration case.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label htmlFor="simulation-transaction" className="sr-only">
            Transaction
          </label>
          <select
            id="simulation-transaction"
            value={selectedId}
            onChange={(event) => handleSelect(event.target.value)}
            className="h-9 w-full max-w-xl rounded-lg border bg-background px-3 font-mono text-xs text-foreground outline-none focus:border-foreground/40"
          >
            {grouped.map(([slug, items]) => (
              <optgroup key={slug} label={scenarioLabel(slug)}>
                {items.map((tx) => (
                  <option key={tx.id} value={tx.id}>
                    {txLabel(tx)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </CardContent>
      </Card>

      {reportError ? (
        <Card size="sm">
          <ErrorState title="Simulation unavailable" description={reportError} />
        </Card>
      ) : currentReport ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <FlaskConical className="size-4 text-muted-foreground" aria-hidden />
              Intervention Comparison
            </CardTitle>
            <CardDescription className="text-xs">
              Baseline vs every available intervention for transaction{" "}
              <span className="font-mono">{selectedId}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SimulationPanel report={currentReport} />
          </CardContent>
        </Card>
      ) : loading ? (
        <Card size="sm">
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Running deterministic simulations…
            </p>
          </CardContent>
        </Card>
      ) : null}

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        The Simulation Lab is deterministic and read-only: it never modifies
        payments, orders, inventory, refunds or webhooks, and it never calls
        an AI. Simulated results are scenario estimates, not guarantees.
      </p>
    </div>
  );
}
