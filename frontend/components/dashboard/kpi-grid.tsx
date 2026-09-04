import type { ApiSummary } from "@/types/api";
import type { KpiSummary } from "@/types/demo";
import { StatCard } from "@/components/shared/stat-card";

function percent(value: number): string {
  return `${value.toFixed(1)}%`;
}

/** Build the four KPI cards from the real deterministic summary. */
function kpisFromSummary(summary: ApiSummary): KpiSummary[] {
  const { total_transactions: total, outcomes } = summary;
  return [
    {
      id: "kpi_payment_success",
      label: "Payment Success",
      value: percent(summary.payment_success_rate),
      tone: "info",
      description: `Share of payments captured (${summary.payment_success_count} of ${total} succeeded, ${summary.payment_failed_count} failed)`,
    },
    {
      id: "kpi_outcome_success",
      label: "Business Outcome Success",
      value: percent(summary.fulfilled_rate),
      tone: "success",
      description: `Journeys classified FULFILLED by the outcome engine (${outcomes.fulfilled} of ${total})`,
    },
    {
      id: "kpi_at_risk",
      label: "At Risk",
      value: percent(summary.at_risk_rate),
      tone: "warning",
      description: `Journeys AT_RISK — a deliberately narrow classification (${outcomes.at_risk} of ${total})`,
    },
    {
      id: "kpi_failed_outcomes",
      label: "Failed Outcomes",
      value: percent(summary.failed_rate),
      tone: "danger",
      description: `Journeys classified FAILED — payment success did not reach the outcome (${outcomes.failed} of ${total})`,
    },
  ];
}

export function KpiGrid({ summary }: { summary: ApiSummary }) {
  const kpis = kpisFromSummary(summary);
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((kpi) => (
          <StatCard key={kpi.id} kpi={kpi} />
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Aggregates from GET /api/v1/summary — computed deterministically by
        the outcome engine across all {summary.total_transactions} seeded
        journeys. No synthetic figures.
      </p>
    </div>
  );
}
