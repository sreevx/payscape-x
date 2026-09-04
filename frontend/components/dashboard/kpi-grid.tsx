import { KPI_SUMMARY } from "@/lib/demo-data";
import { StatCard } from "@/components/shared/stat-card";

export function KpiGrid() {
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {KPI_SUMMARY.map((kpi) => (
          <StatCard key={kpi.id} kpi={kpi} />
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Sample KPIs — illustrative. Per-journey evidence, consistency and
        outcomes are computed by the live engines on each transaction page.
      </p>
    </div>
  );
}