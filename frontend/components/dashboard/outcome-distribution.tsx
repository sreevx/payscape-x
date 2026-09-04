import { BarChart3 } from "lucide-react";

import type { ApiSummary } from "@/types/api";
import type { Tone } from "@/types/demo";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const SLICE_COLORS: Record<Tone, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-blue-500",
  neutral: "bg-zinc-300 dark:bg-zinc-600",
};

interface DistributionSlice {
  label: string;
  count: number;
  tone: Tone;
  note: string;
}

function slicesFromSummary(summary: ApiSummary): DistributionSlice[] {
  const { outcomes } = summary;
  return [
    {
      label: "FULFILLED",
      count: outcomes.fulfilled,
      tone: "success",
      note: "Intended outcome achieved end to end",
    },
    {
      label: "AT_RISK",
      count: outcomes.at_risk,
      tone: "warning",
      note: "Recoverable but unproven — narrow rule",
    },
    {
      label: "FAILED",
      count: outcomes.failed,
      tone: "danger",
      note: "Payment success did not reach the outcome",
    },
    {
      label: "UNVERIFIABLE",
      count: outcomes.unverifiable,
      tone: "neutral",
      note: "Missing or contradictory evidence",
    },
  ];
}

export function OutcomeDistribution({ summary }: { summary: ApiSummary }) {
  const total = summary.total_transactions;
  const slices = slicesFromSummary(summary);

  const label = slices
    .filter((slice) => slice.count > 0)
    .map((slice) => `${slice.label} ${((slice.count / total) * 100).toFixed(1)}%`)
    .join(", ");

  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Outcome Distribution</CardTitle>
        <CardDescription className="text-xs">
          Deterministic business outcomes across all {total} seeded journeys
        </CardDescription>
        <CardAction>
          <BarChart3 className="size-4 text-muted-foreground" aria-hidden />
        </CardAction>
      </CardHeader>
      <CardContent className="flex h-full flex-col justify-between gap-4">
        <div>
          <div
            className="flex h-3 w-full overflow-hidden rounded-full"
            role="img"
            aria-label={`Outcome distribution: ${label}`}
          >
            {slices.map((slice) => (
              <div
                key={slice.label}
                className={cn("h-full", SLICE_COLORS[slice.tone])}
                style={{ width: `${(slice.count / total) * 100}%` }}
                title={`${slice.label} ${slice.count} (${((slice.count / total) * 100).toFixed(1)}%)`}
              />
            ))}
          </div>

          <div className="mt-4 space-y-2.5">
            {slices.map((slice) => (
              <div key={slice.label} className="flex items-center gap-2">
                <span
                  className={cn("size-2 shrink-0 rounded-sm", SLICE_COLORS[slice.tone])}
                  aria-hidden
                />
                <span className="w-24 text-xs font-medium text-foreground">
                  {slice.label}
                </span>
                <span className="font-mono text-xs tabular-nums text-foreground">
                  {((slice.count / total) * 100).toFixed(1)}%
                </span>
                <span className="hidden truncate text-[11px] text-muted-foreground sm:block">
                  {slice.count} · {slice.note}
                </span>
              </div>
            ))}
          </div>
        </div>

        <p className="flex items-center gap-1.5 border-t pt-3 text-[11px] text-muted-foreground">
          <BarChart3 className="size-3.5 shrink-0" aria-hidden />
          Classified by the deterministic outcome engine — every verdict is
          rule-traced on the transaction page.
        </p>
      </CardContent>
    </Card>
  );
}
