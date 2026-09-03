import Link from "next/link";
import { GitBranch } from "lucide-react";

import { getFailures } from "@/lib/api-client";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { ErrorState } from "@/components/shared/states";
import type { Tone } from "@/types/demo";

export const metadata = {
  title: "Failure Patterns",
};

export const dynamic = "force-dynamic";

const SEVERITY_TONES: Record<string, Tone> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "neutral",
};

export default async function FailuresPage() {
  let data;
  try {
    data = await getFailures({ limit: 100 });
  } catch {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <PageHeader
          title="Failure Patterns"
          subtitle="Detected compound failures where successful payments do not reach their intended outcome."
        />
        <Card size="sm">
          <ErrorState
            title="Failures engine unavailable"
            description="The failures API could not be reached. Start the backend and seed the database, then try again."
          />
        </Card>
      </div>
    );
  }

  const items = data.items;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Failure Patterns"
        subtitle="Compound failures detected deterministically across the seeded journeys — related problems chained across the payment-to-delivery promise stages."
        actions={
          <StatusBadge tone="neutral">
            {data.total} DETECTED
          </StatusBadge>
        }
      />

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Detected Compound Failures</CardTitle>
          <CardDescription className="text-xs">
            Computed by the Part 6 Compound Failure Engine over the real
            journey / evidence / consistency / outcome APIs
          </CardDescription>
          <CardAction>
            <GitBranch className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent className="px-0">
          {items.length === 0 ? (
            <p className="px-4 pb-4 text-xs text-muted-foreground">
              No compound failures detected in the current dataset.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Transaction</TableHead>
                  <TableHead>Root cause</TableHead>
                  <TableHead>Chain</TableHead>
                  <TableHead className="text-right">Severity</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="pr-4">Classification</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.transaction_id}>
                    <TableCell className="pl-4">
                      <Link
                        href={`/transactions/${item.transaction_id}`}
                        className="text-xs font-medium text-foreground hover:underline"
                      >
                        {item.external_order_id || item.transaction_id}
                      </Link>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {item.scenario_slug} · {item.transaction_id.slice(0, 8)}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-56">
                      <span className="block text-xs font-medium text-foreground">
                        {item.primary_failure_label ?? "—"}
                      </span>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {item.root_cause_kinds.join(", ") || "—"}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.chain_length} nodes · {item.distinct_stages.join(" → ").toLowerCase()}
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusBadge tone={SEVERITY_TONES[item.severity] ?? "neutral"}>
                        {item.severity}
                      </StatusBadge>
                    </TableCell>
                    <TableCell className="text-xs">
                      <span className="text-muted-foreground">{item.scope}</span>
                      {item.scope === "MULTI_TRANSACTION" ? (
                        <span className="block font-mono text-[10px] text-muted-foreground">
                          {item.affected_transactions} tx · {item.shared_skus.join(", ")}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <StatusBadge tone="danger">{item.outcome}</StatusBadge>
                    </TableCell>
                    <TableCell className="pr-4">
                      <StatusBadge
                        tone={
                          item.classification === "OBSERVED" ? "success" : "info"
                        }
                      >
                        {item.classification}
                      </StatusBadge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Each row is a transaction whose failure chain spans multiple promise
        stages — root cause, chain length and scope are deterministic. A
        MULTI_TRANSACTION scope means the same stock shortage hit other orders
        (shared SKU on the OUT_OF_STOCK records).
      </p>
    </div>
  );
}
