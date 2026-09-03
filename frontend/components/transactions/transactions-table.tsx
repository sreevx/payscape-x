"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";

import type { ApiPaymentStatus, ApiTransactionListItem } from "@/types/api";
import { formatCurrencyCompact, formatDateTime } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/** Presentational mapping from backend payment status to a state tone. */
const PAYMENT_STATUS_TONES: Record<ApiPaymentStatus, Tone> = {
  CREATED: "neutral",
  AUTHORIZED: "info",
  CAPTURED: "success",
  FAILED: "danger",
  REFUNDED: "info",
  PARTIALLY_REFUNDED: "warning",
};

function scenarioLabel(slug: string | null): string {
  if (!slug) return "—";
  return slug.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function TransactionsTable({
  transactions,
  total,
}: {
  transactions: ApiTransactionListItem[];
  total: number;
}) {
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return transactions;
    return transactions.filter((tx) =>
      [
        tx.id,
        tx.external_order_id,
        tx.customer_name,
        tx.customer_email,
        tx.provider,
        tx.payment_status,
        tx.scenario_slug ?? "",
      ].some((value) => value.toLowerCase().includes(q))
    );
  }, [query, transactions]);

  return (
    <div className="space-y-3">
      <div className="relative w-full max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter by transaction, order, customer, provider…"
          aria-label="Filter transactions"
          className="h-8 pl-8 text-xs"
        />
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-3">Transaction</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Payment Status</TableHead>
              <TableHead>Scenario</TableHead>
              <TableHead className="text-right">Events</TableHead>
              <TableHead className="pr-3 text-right">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((tx) => (
              <TableRow key={tx.id}>
                <TableCell className="pl-3">
                  <Link
                    href={`/transactions/${tx.id}`}
                    className="block font-mono text-xs text-foreground hover:underline"
                  >
                    {tx.id}
                  </Link>
                  <span className="block text-[11px] text-muted-foreground">
                    {tx.external_order_id}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="block text-xs text-foreground">
                    {tx.customer_name}
                  </span>
                  <span className="block text-[11px] text-muted-foreground">
                    {tx.customer_email}
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {formatCurrencyCompact(tx.amount, tx.currency)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {tx.provider}
                  {tx.method ? (
                    <span className="block text-[10px] uppercase">
                      {tx.method}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell>
                  <StatusBadge tone={PAYMENT_STATUS_TONES[tx.payment_status]}>
                    {tx.payment_status}
                  </StatusBadge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {scenarioLabel(tx.scenario_slug)}
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                  {tx.event_count}
                </TableCell>
                <TableCell className="pr-3 text-right text-xs text-muted-foreground">
                  {formatDateTime(tx.created_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {rows.length === 0 ? (
          <div className="border-t p-4">
            <EmptyState
              title="No transactions match your filter"
              description="Try a different transaction ID, order ID, customer or provider."
            />
          </div>
        ) : null}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {rows.length} of {total} transactions · synthetic data from the
        backend event pipeline
      </p>
    </div>
  );
}