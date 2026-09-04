import Link from "next/link";
import { ListChecks } from "lucide-react";

import { getDecisions } from "@/lib/api-client";
import { formatCurrency, formatDateTime } from "@/lib/format";
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
  title: "Action Center",
};

export const dynamic = "force-dynamic";

const OUTCOME_TONES: Record<string, Tone> = {
  FULFILLED: "success",
  AT_RISK: "warning",
  FAILED: "danger",
  UNVERIFIABLE: "neutral",
};

const APPROVAL_TONES: Record<string, Tone> = {
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
};

function truncate(text: string, max = 180): string {
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export default async function ActionsPage() {
  let data;
  try {
    data = await getDecisions();
  } catch {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <PageHeader
          title="Action Center"
          subtitle="Recommended actions on at-risk and failed outcomes — with human approval before execution."
        />
        <Card size="sm">
          <ErrorState
            title="Action Center unavailable"
            description="The decisions API could not be reached. Start the backend and seed the database, then try again."
          />
        </Card>
      </div>
    );
  }

  const items = data.items;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Action Center"
        subtitle="Recommended actions on at-risk and failed outcomes — with human approval before execution."
        actions={
          <StatusBadge tone="neutral">
            {data.total} DECISIONS RECORDED
          </StatusBadge>
        }
      />

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Decision Queue</CardTitle>
          <CardDescription className="text-xs">
            Every row is a real auditable recommendation from the Part 8
            Decision Agent, generated when the transaction was opened for
            investigation — outcome, action, confidence and source are
            recorded, never fabricated
          </CardDescription>
          <CardAction>
            <ListChecks className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent className="px-0">
          {items.length === 0 ? (
            <div className="px-4 pb-4">
              <p className="text-xs text-muted-foreground">
                No decisions recorded yet. Decisions are generated
                deterministically when a transaction is opened — visit the{" "}
                <Link
                  href="/transactions"
                  className="font-medium text-foreground underline underline-offset-2 hover:text-muted-foreground"
                >
                  Transactions
                </Link>{" "}
                page to start one.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Transaction</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Recommendation</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Approval</TableHead>
                  <TableHead className="pr-4 text-right">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.decision_id}>
                    <TableCell className="pl-4">
                      <Link
                        href={`/transactions/${item.transaction_id}`}
                        className="text-xs font-medium text-foreground hover:underline"
                      >
                        {item.external_order_id}
                      </Link>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {formatCurrency(item.amount, item.currency)} ·{" "}
                        {item.transaction_id.slice(0, 8)} ·{" "}
                        {item.payment_status}
                      </span>
                    </TableCell>
                    <TableCell>
                      {item.outcome ? (
                        <StatusBadge
                          tone={OUTCOME_TONES[item.outcome] ?? "neutral"}
                        >
                          {item.outcome}
                        </StatusBadge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-72">
                      <span className="font-mono text-xs font-semibold text-foreground">
                        {item.recommended_action}
                      </span>
                      <span
                        title={item.reason}
                        className="mt-0.5 block text-[10px] leading-relaxed text-muted-foreground"
                      >
                        {truncate(item.reason)}
                      </span>
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <span className="text-xs font-semibold tabular-nums text-foreground">
                        {Math.round(item.decision_confidence * 100)}%
                      </span>
                      <span className="block text-[10px] text-muted-foreground">
                        decision
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        tone={item.decision_source === "LLM" ? "info" : "neutral"}
                      >
                        {item.decision_source === "LLM" ? "AI" : "CODE"}
                      </StatusBadge>
                      <span className="block font-mono text-[9px] text-muted-foreground">
                        {item.decision_id.slice(0, 8)}…
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        tone={APPROVAL_TONES[item.approval_status] ?? "neutral"}
                      >
                        {item.approval_status}
                      </StatusBadge>
                    </TableCell>
                    <TableCell className="pr-4 text-right text-xs text-muted-foreground">
                      {item.created_at ? formatDateTime(item.created_at) : "—"}
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
        Open a row to review its evidence and Approve / Reject on the
        transaction&apos;s &ldquo;What Should We Do?&rdquo; panel. Nothing here
        executes automatically — recording approval never touches money or
        customer communication.
      </p>
    </div>
  );
}
