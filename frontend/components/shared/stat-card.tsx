import type { KpiSummary } from "@/types/demo";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DemoTag } from "@/components/shared/demo-tag";

const TONE_ACCENT: Record<KpiSummary["tone"], string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-blue-500",
  neutral: "bg-zinc-400",
};

export function StatCard({ kpi }: { kpi: KpiSummary }) {
  return (
    <Card size="sm" className="gap-2">
      <CardHeader className="gap-0">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            {kpi.label}
          </CardTitle>
          <DemoTag />
        </div>
        <CardDescription className="text-xs">{kpi.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-baseline gap-2 pt-0">
        <span
          className={cn(
            "h-2 w-1 shrink-0 self-center rounded-full",
            TONE_ACCENT[kpi.tone]
          )}
          aria-hidden
        />
        <span className="font-mono text-2xl font-semibold tracking-tight tabular-nums">
          {kpi.value}
        </span>
      </CardContent>
      <div className="px-(--card-spacing) pb-(--card-spacing) text-xs text-muted-foreground">
        {kpi.delta}
      </div>
    </Card>
  );
}