import { TrendingDown, TrendingUp, TriangleAlert } from "lucide-react";

import { FAILURE_PATTERNS } from "@/lib/demo-data";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/status-badge";
import { DemoTag } from "@/components/shared/demo-tag";

export function FailurePatterns() {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm">Emerging Failure Patterns</CardTitle>
        <CardDescription className="text-xs">
          Recurring failure modes observed across the event stream
        </CardDescription>
        <CardAction>
          <DemoTag />
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {FAILURE_PATTERNS.map((pattern) => (
            <div
              key={pattern.id}
              className="flex flex-col gap-2 rounded-lg border p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <TriangleAlert
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    pattern.status === "emerging"
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-muted-foreground"
                  )}
                  aria-hidden
                />
                <StatusBadge
                  tone={pattern.trend === "rising" ? "warning" : pattern.trend === "declining" ? "success" : "neutral"}
                >
                  {pattern.trend}
                </StatusBadge>
              </div>
              <div>
                <p className="text-[13px] leading-snug font-medium text-foreground">
                  {pattern.name}
                </p>
                <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                  {pattern.description}
                </p>
              </div>
              <div className="mt-auto flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
                <span>
                  <span className="font-mono font-semibold text-foreground">
                    {pattern.transactions}
                  </span>{" "}
                  txns · {pattern.impact}
                </span>
                <span className="inline-flex items-center gap-0.5">
                  {pattern.trend === "rising" ? (
                    <TrendingUp className="size-3 text-amber-600" aria-hidden />
                  ) : pattern.trend === "declining" ? (
                    <TrendingDown className="size-3 text-emerald-600" aria-hidden />
                  ) : null}
                  {formatDate(pattern.firstSeen)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}