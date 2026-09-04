"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, RefreshCw, Search } from "lucide-react";

import { ApiError, getEvents } from "@/lib/api-client";
import type { ApiEventStreamItem } from "@/types/api";
import { API_EVENT_SOURCES, API_EVENT_TYPE_GROUPS } from "@/types/api";
import { formatDateTime } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/states";

const PAGE_SIZE = 50;

/** Compact payload summary: a few key/value pairs, truncated. */
function payloadSummary(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).slice(0, 4);
  if (entries.length === 0) return "no payload";
  return entries
    .map(([key, value]) => `${key}=${String(value).slice(0, 32)}`)
    .join(" · ");
}

export default function EventsPage() {
  const [eventType, setEventType] = useState("");
  const [source, setSource] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [applied, setApplied] = useState({ eventType: "", source: "", correlationId: "" });
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<ApiEventStreamItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ApiEventStreamItem | null>(null);

  const load = useCallback(async (nextOffset: number) => {
    setError(null);
    setItems(null);
    try {
      const response = await getEvents({
        limit: PAGE_SIZE,
        offset: nextOffset,
        eventType: applied.eventType || undefined,
        source: applied.source || undefined,
        correlationId: applied.correlationId.trim() || undefined,
      });
      setItems(response.items);
      setTotal(response.total);
      setOffset(nextOffset);
      setSelected(null);
    } catch (cause) {
      setItems([]);
      setTotal(0);
      setError(
        cause instanceof ApiError
          ? "The event stream API is unreachable. Start the backend and seed the database."
          : "The event stream could not be loaded. Try again shortly."
      );
    }
  }, [applied]);

  // Initial load (and re-load whenever the applied filters change). The
  // probe is deferred out of the effect body so state updates resolve on
  // the fetch result, not synchronously inside the effect.
  useEffect(() => {
    const first = window.setTimeout(() => void load(0), 0);
    return () => window.clearTimeout(first);
  }, [load]);

  const applyFilters = () => {
    setApplied({ eventType, source, correlationId });
  };

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Event Explorer"
        subtitle="Raw structured event stream — the single source of truth every PAYSCAPE-X module consumes."
      />

      {/* Filters */}
      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Filters</CardTitle>
          <CardDescription className="text-xs">
            Query the unified event stream by type, source or correlation ID
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex min-w-44 flex-col gap-1 text-[11px] font-medium text-muted-foreground">
              Event type
              <select
                value={eventType}
                onChange={(event) => setEventType(event.target.value)}
                className="h-8 rounded-md border bg-background px-2 text-xs text-foreground"
              >
                <option value="">All types</option>
                {Object.entries(API_EVENT_TYPE_GROUPS).map(([group, types]) => (
                  <optgroup key={group} label={group}>
                    {types.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>

            <label className="flex min-w-40 flex-col gap-1 text-[11px] font-medium text-muted-foreground">
              Source
              <select
                value={source}
                onChange={(event) => setSource(event.target.value)}
                className="h-8 rounded-md border bg-background px-2 text-xs text-foreground"
              >
                <option value="">All sources</option>
                {API_EVENT_SOURCES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex min-w-56 flex-col gap-1 text-[11px] font-medium text-muted-foreground">
              Correlation ID
              <input
                type="text"
                value={correlationId}
                onChange={(event) => setCorrelationId(event.target.value)}
                placeholder="uuid of a journey"
                className="h-8 rounded-md border bg-background px-2 font-mono text-xs text-foreground"
              />
            </label>

            <button
              type="button"
              onClick={applyFilters}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium hover:bg-muted"
            >
              <Search className="size-3.5" aria-hidden /> Apply
            </button>
            {applied.eventType || applied.source || applied.correlationId ? (
              <button
                type="button"
                onClick={() => {
                  setEventType("");
                  setSource("");
                  setCorrelationId("");
                  setApplied({ eventType: "", source: "", correlationId: "" });
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="size-3.5" aria-hidden /> Reset
              </button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {/* Stream */}
      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Event Stream</CardTitle>
          <CardDescription className="text-xs">
            {items === null
              ? "Loading the latest events…"
              : `${total.toLocaleString()} events · page ${currentPage} of ${pageCount}`}
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {items === null ? (
            <div className="px-4 pb-4">
              <LoadingState rows={6} />
            </div>
          ) : error ? (
            <div className="px-4 pb-4">
              <ErrorState
                title="Event stream unavailable"
                description={error}
                onRetry={() => void load(offset)}
              />
            </div>
          ) : items.length === 0 ? (
            <div className="px-4 pb-4">
              <EmptyState
                title="No events match these filters"
                description="Try a different event type, source or correlation ID."
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Event</TableHead>
                  <TableHead>Order</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Payload</TableHead>
                  <TableHead>Correlation</TableHead>
                  <TableHead className="pr-4 text-right">Timestamp</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((event) => (
                  <TableRow
                    key={event.id}
                    className={event.id === selected?.id ? "bg-muted/50" : undefined}
                    onMouseEnter={() => setSelected(event)}
                  >
                    <TableCell className="pl-4">
                      <StatusBadge tone="info">{event.event_type}</StatusBadge>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {event.id}
                      </span>
                    </TableCell>
                    <TableCell>
                      {event.payment_id ? (
                        <Link
                          href={`/transactions/${event.payment_id}`}
                          className="block font-mono text-[11px] text-foreground hover:underline"
                        >
                          {event.external_order_id}
                        </Link>
                      ) : (
                        <span className="block font-mono text-[11px] text-foreground">
                          {event.external_order_id}
                        </span>
                      )}
                      <span className="block text-[10px] text-muted-foreground">
                        {event.payment_id ?? "no payment"}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {event.source}
                    </TableCell>
                    <TableCell className="max-w-md font-mono text-[11px] text-muted-foreground">
                      {payloadSummary(event.payload)}
                    </TableCell>
                    <TableCell className="font-mono text-[10px] text-muted-foreground">
                      {event.correlation_id}
                    </TableCell>
                    <TableCell className="pr-4 text-right text-xs text-muted-foreground">
                      {formatDateTime(event.timestamp)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Event detail panel */}
      {selected ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-sm">Event Detail</CardTitle>
            <CardDescription className="text-xs">
              {selected.event_type} · {selected.source} ·{" "}
              {formatDateTime(selected.timestamp)}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
            <div className="space-y-1">
              <p className="text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
                Identity
              </p>
              <p className="font-mono break-all text-muted-foreground">{selected.id}</p>
              <p className="text-muted-foreground">
                idempotency: {selected.idempotency_key ?? "none"}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
                Correlation
              </p>
              <p className="font-mono break-all text-muted-foreground">
                {selected.correlation_id}
              </p>
              <p className="text-muted-foreground">
                order {selected.order_id}
                {selected.payment_id ? ` · payment ${selected.payment_id}` : ""}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
                Payload
              </p>
              <pre className="overflow-x-auto rounded-md bg-muted p-2 font-mono text-[10px] leading-relaxed text-foreground">
                {JSON.stringify(selected.payload, null, 2)}
              </pre>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Pagination */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">
          {items === null || error
            ? "Events load from the backend API"
            : `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
        </p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={offset === 0 || items === null}
            onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
            className="inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium disabled:opacity-40"
          >
            <ChevronLeft className="size-3.5" aria-hidden /> Prev
          </button>
          <span className="px-2 text-xs text-muted-foreground tabular-nums">
            {currentPage} / {pageCount}
          </span>
          <button
            type="button"
            disabled={items === null || offset + PAGE_SIZE >= total}
            onClick={() => void load(offset + PAGE_SIZE)}
            className="inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium disabled:opacity-40"
          >
            Next <ChevronRight className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        Structured events are the contract every module consumes: each event
        carries type, source, timestamp, correlation and payload — the same
        stream behind journey reconstruction and outcome analysis.
      </p>
    </div>
  );
}