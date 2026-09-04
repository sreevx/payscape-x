import { BarChart3 } from "lucide-react";

import { OUTCOME_DISTRIBUTION } from "@/lib/demo-data";
import type { Tone } from "@/types/demo";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DemoTag } from "@/components/shared/demo-tag";

const SLICE_COLORS: Record<Tone, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  info: "bg-blue-500",
  neutral: "bg-zinc-300 dark:bg-zinc-600",
};

export function OutcomeDistribution() {
  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Outcome Distribution</CardTitle>
        <CardDescription className="text-xs">
          Share of outcomes across captured payments · last 7 days
        </CardDescription>
        <CardAction>
          <DemoTag />
        </CardAction>
      </CardHeader>
      <CardContent className="flex h-full flex-col justify-between gap-4">
        {/* Stacked bar (placeholder visualization, not a real chart) */}
        <div>
          <div
            className="flex h-3 w-full overflow-hidden rounded-full"
            role="img"
            aria-label="Outcome distribution: fulfilled 94.1%, at risk 3.7%, failed 2.2%"
          >
            {OUTCOME_DISTRIBUTION.map((slice) => (
              <div
                key={slice.label}
                className={cn("h-full", SLICE_COLORS[slice.tone])}
                style={{ width: `${slice.value}%` }}
                title={`${slice.label} ${slice.value}%`}
              />
            ))}
          </div>

          <div className="mt-4 space-y-2.5">
            {OUTCOME_DISTRIBUTION.map((slice) => (
              <div key={slice.label} className="flex items-center gap-2">
                <span
                  className={cn("size-2 shrink-0 rounded-sm", SLICE_COLORS[slice.tone])}
                  aria-hidden
                />
                <span className="w-24 text-xs font-medium text-foreground">
                  {slice.label}
                </span>
                <span className="font-mono text-xs tabular-nums text-foreground">
                  {slice.value.toFixed(1)}%
                </span>
                <span className="hidden truncate text-[11px] text-muted-foreground sm:block">
                  {slice.note}
                </span>
              </div>
            ))}
          </div>
        </div>

        <p className="flex items-center gap-1.5 border-t pt-3 text-[11px] text-muted-foreground">
          <BarChart3 className="size-3.5 shrink-0" aria-hidden />
          Sample distribution — illustrative. Live per-journey outcomes are on
          each transaction page.
        </p>
      </CardContent>
    </Card>
  );
}