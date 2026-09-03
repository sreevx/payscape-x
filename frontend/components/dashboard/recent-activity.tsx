import Link from "next/link";
import {
  CircleAlert,
  FlaskConical,
  ListChecks,
  Radio,
  RefreshCw,
  SearchCheck,
  TriangleAlert,
} from "lucide-react";

import { RECENT_ACTIVITY } from "@/lib/demo-data";
import type { ActivityItem } from "@/types/demo";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DemoTag } from "@/components/shared/demo-tag";

const KIND_META: Record<ActivityItem["kind"], { icon: typeof Radio; color: string; label: string }> = {
  investigation: { icon: SearchCheck, color: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400", label: "Investigation" },
  event: { icon: Radio, color: "bg-zinc-100 text-zinc-600 dark:bg-zinc-500/15 dark:text-zinc-400", label: "Event stream" },
  pattern: { icon: TriangleAlert, color: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400", label: "Failure pattern" },
  outcome: { icon: CircleAlert, color: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400", label: "Outcome" },
  refund: { icon: RefreshCw, color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400", label: "Refund" },
  alert: { icon: ListChecks, color: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400", label: "Alert" },
};

export function RecentActivity() {
  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Recent Activity</CardTitle>
        <CardDescription className="text-xs">
          Latest actions across investigations and the event stream
        </CardDescription>
        <CardAction>
          <DemoTag />
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <ol className="space-y-0 px-(--card-spacing)">
          {RECENT_ACTIVITY.map((item) => {
            const meta = KIND_META[item.kind];
            return (
              <li key={item.id} className="relative flex gap-3 pb-4 last:pb-0">
                {item !== RECENT_ACTIVITY[RECENT_ACTIVITY.length - 1] ? (
                  <span
                    aria-hidden
                    className="absolute top-7 left-[13px] h-[calc(100%-1.5rem)] w-px bg-border"
                  />
                ) : null}
                <span
                  className={cn(
                    "z-10 flex size-7 shrink-0 items-center justify-center rounded-full",
                    meta.color
                  )}
                >
                  <meta.icon className="size-3.5" aria-hidden />
                </span>
                <div className="min-w-0 pt-0.5">
                  <p className="text-xs leading-snug text-foreground">
                    <span className="font-medium">{meta.label}</span>{" "}
                    <span className="text-muted-foreground">{item.message}</span>
                  </p>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span>{timeAgo(item.timestamp)}</span>
                    {item.transactionId ? (
                      <Link
                        href={`/transactions/${item.transactionId}`}
                        className="font-mono text-foreground/70 hover:underline"
                      >
                        {item.transactionId}
                      </Link>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
        <div className="mt-3 border-t px-(--card-spacing) pt-2 text-[11px] text-muted-foreground">
          <FlaskConical className="mr-1 inline size-3 align-[-1px]" aria-hidden />
          Activity is placeholder data until the event pipeline goes live.
        </div>
      </CardContent>
    </Card>
  );
}