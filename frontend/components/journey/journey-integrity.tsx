import type { ApiJourneyIntegrity } from "@/types/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Journey integrity panel (Part 3).
 *
 * Displays the structural integrity report. Every finding is an observation
 * about what the raw event stream contains — duplicates, missing-event
 * candidates, contradictions, delayed, out-of-order, unknown and orphan
 * events. No outcome classification is ever shown here.
 */

function Chip({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "success" | "warning" | "danger" | "neutral";
}) {
  const tones = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400",
    warning:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400",
    danger:
      "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400",
    neutral:
      "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-500/30 dark:bg-zinc-500/10 dark:text-zinc-300",
  };
  return (
    <div className={cn("rounded-lg border px-3 py-2", tones[tone])}>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      <p className="text-[10px] font-medium tracking-wide uppercase opacity-80">
        {label}
      </p>
    </div>
  );
}

function FindingCard({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "warning" | "danger" | "info" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        tone === "danger" && "border-red-200 bg-red-50/40 dark:border-red-500/20 dark:bg-red-500/5",
        tone === "warning" &&
          "border-amber-200 bg-amber-50/40 dark:border-amber-500/20 dark:bg-amber-500/5",
        tone === "info" && "border-blue-200 bg-blue-50/40 dark:border-blue-500/20 dark:bg-blue-500/5",
        tone === "neutral" &&
          "border-zinc-200 bg-zinc-50/40 dark:border-zinc-500/20 dark:bg-zinc-500/5"
      )}
    >
      <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
        {title}
      </p>
      {children}
    </div>
  );
}

export function JourneyIntegrity({
  integrity,
}: {
  integrity: ApiJourneyIntegrity;
}) {
  const hasFindings =
    integrity.missing_expected_event_candidates.length > 0 ||
    integrity.contradictions.length > 0 ||
    integrity.duplicates.length > 0 ||
    integrity.delayed_events.length > 0 ||
    integrity.out_of_order_events.length > 0 ||
    integrity.unknown_events.length > 0 ||
    integrity.orphan_events.length > 0;

  return (
    <div className="space-y-4">
      {/* Counts */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Chip label="Events" value={integrity.total_events} />
        <Chip label="Linked" value={integrity.linked_events} tone="success" />
        <Chip
          label="Duplicates"
          value={integrity.duplicate_count}
          tone={integrity.duplicate_count ? "warning" : "neutral"}
        />
        <Chip
          label="Unknown"
          value={integrity.unknown_count}
          tone={integrity.unknown_count ? "danger" : "neutral"}
        />
        <Chip
          label="Orphans"
          value={integrity.orphan_count}
          tone={integrity.orphan_count ? "warning" : "neutral"}
        />
        <Chip
          label="Delayed"
          value={integrity.delayed_count}
          tone={integrity.delayed_count ? "warning" : "neutral"}
        />
        <Chip
          label="Out-of-order"
          value={integrity.out_of_order_count}
          tone={integrity.out_of_order_count ? "warning" : "neutral"}
        />
        <Chip
          label="Duration"
          value={
            integrity.duration_seconds === null
              ? "—"
              : `${Math.round(integrity.duration_seconds / 3600)}h`
          }
        />
      </div>

      {!hasFindings ? (
        <p className="text-xs text-muted-foreground">
          No structural findings: every expected event is present, no
          duplicates, delays, contradictions, unknowns or orphans were
          recorded in this journey.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {/* Missing-event candidates */}
          {integrity.missing_expected_event_candidates.length > 0 && (
            <FindingCard title="Missing-event candidates" tone="warning">
              <ul className="space-y-1.5">
                {integrity.missing_expected_event_candidates.map((candidate) => (
                  <li
                    key={`${candidate.event_type}:${candidate.rule_id}`}
                    className="text-[11px]"
                  >
                    <span className="font-mono font-medium text-foreground">
                      {candidate.event_type}
                    </span>
                    <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                      {candidate.rule_id}
                    </span>
                    <p className="mt-0.5 text-muted-foreground">{candidate.note}</p>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Contradictions */}
          {integrity.contradictions.length > 0 && (
            <FindingCard title="Contradictions" tone="danger">
              <ul className="space-y-2">
                {integrity.contradictions.map((contradiction) => (
                  <li key={contradiction.rule_id} className="text-[11px]">
                    <p className="font-medium text-foreground">
                      {contradiction.type}{" "}
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {contradiction.rule_id}
                      </span>
                    </p>
                    <p className="mt-0.5 text-muted-foreground">
                      {contradiction.explanation}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      {contradiction.involved_event_ids.length} events ·{" "}
                      {contradiction.timestamps
                        .map((stamp) => formatDateTime(stamp))
                        .join(" → ")}
                    </p>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Duplicates */}
          {integrity.duplicates.length > 0 && (
            <FindingCard title="Duplicates" tone="warning">
              <ul className="space-y-1.5">
                {integrity.duplicates.map((duplicate) => (
                  <li
                    key={`${duplicate.event_id}:${duplicate.rule_id}`}
                    className="text-[11px]"
                  >
                    <span className="font-mono font-medium text-foreground">
                      {duplicate.event_type}
                    </span>
                    <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                      {duplicate.rule_id}
                    </span>
                    <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      key={duplicate.idempotency_key} · canonical=
                      {duplicate.canonical_event_id.slice(0, 8)}…
                    </p>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Delayed webhooks */}
          {integrity.delayed_events.length > 0 && (
            <FindingCard title="Delayed webhooks" tone="warning">
              <ul className="space-y-1">
                {integrity.delayed_events.map((delayed) => (
                  <li
                    key={delayed.event_id}
                    className="font-mono text-[11px] text-foreground"
                  >
                    {delayed.event_type}
                    <span className="ml-2 text-muted-foreground">
                      {delayed.delay_minutes === null
                        ? "flagged delayed"
                        : `~${Math.round(delayed.delay_minutes / 60)}h late`}
                    </span>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Out-of-order */}
          {integrity.out_of_order_events.length > 0 && (
            <FindingCard title="Out-of-order ingestion" tone="warning">
              <ul className="space-y-1">
                {integrity.out_of_order_events.map((item) => (
                  <li
                    key={item.event_id}
                    className="font-mono text-[11px] text-foreground"
                  >
                    {item.event_type} · ingested at #{item.ingestion_position},
                    chronological #{item.chronological_position}
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Unknown events */}
          {integrity.unknown_events.length > 0 && (
            <FindingCard title="Unknown events" tone="danger">
              <ul className="space-y-1">
                {integrity.unknown_events.map((item) => (
                  <li key={item.event_id} className="font-mono text-[11px]">
                    <span className="text-foreground">{item.event_type}</span>
                    <span className="ml-2 text-muted-foreground">{item.reason}</span>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}

          {/* Orphans */}
          {integrity.orphan_events.length > 0 && (
            <FindingCard title="Orphan events" tone="neutral">
              <ul className="space-y-1">
                {integrity.orphan_events.map((item) => (
                  <li key={item.event_id} className="font-mono text-[11px]">
                    <span className="text-foreground">{item.event_type}</span>
                    <span className="ml-2 text-muted-foreground">
                      correlation {item.correlation_id.slice(0, 8)}… — {item.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </FindingCard>
          )}
        </div>
      )}

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Structural observations only — the reconstruction engine describes
        what happened and never classifies the business outcome.
      </p>
    </div>
  );
}