import type { ApiEvidenceItem, ApiEvidenceReport } from "@/types/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Evidence panel (Part 4).
 *
 * Renders the deterministic evidence report: what the records actually
 * support, evidence gaps (structural observations) and contradictions
 * (preserved, never resolved). No outcome classification is ever shown.
 */

const STRENGTH_TONES: Record<ApiEvidenceItem["strength"], Tone> = {
  DIRECT: "info",
  CORROBORATED: "success",
  INDIRECT: "neutral",
  MISSING: "warning",
  CONTRADICTED: "danger",
};

const STRENGTH_LABEL: Record<ApiEvidenceItem["strength"], string> = {
  DIRECT: "DIRECT",
  CORROBORATED: "CORROBORATED",
  INDIRECT: "INDIRECT",
  MISSING: "MISSING",
  CONTRADICTED: "CONTRADICTED",
};

function supportingDataSummary(data: Record<string, unknown>): string {
  const entries = Object.entries(data).filter(
    ([key]) => key !== "events" && key !== "corroboration"
  );
  const parts = entries
    .slice(0, 3)
    .map(([key, value]) => `${key}=${String(value).slice(0, 36)}`);
  const events = Array.isArray(data.events) ? data.events.length : 0;
  if (events > 0) parts.unshift(`events=${events}`);
  if (data.corroboration && typeof data.corroboration === "object") {
    const record = (data.corroboration as Record<string, unknown>).record;
    if (record) parts.push(`corroborated by ${String(record)}`);
  }
  return parts.length ? parts.join(" · ") : "no supporting data";
}

function EvidenceCard({ item }: { item: ApiEvidenceItem }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusBadge tone={STRENGTH_TONES[item.strength]}>
          {STRENGTH_LABEL[item.strength]}
        </StatusBadge>
        <span className="text-xs font-medium text-foreground">{item.claim}</span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {item.rule_id}
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
        {supportingDataSummary(item.supporting_data)}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground/80">
        <span>
          category <span className="font-mono">{item.category}</span>
        </span>
        <span>
          confidence{" "}
          <span className="font-mono tabular-nums">{item.confidence.toFixed(1)}</span>
        </span>
        {item.timestamp ? (
          <span>{formatDateTime(item.timestamp)}</span>
        ) : null}
        {item.event_ids.length > 0 ? (
          <span className="font-mono">
            {item.event_ids.length} event{item.event_ids.length === 1 ? "" : "s"} ·{" "}
            {item.event_ids[0].slice(0, 8)}…
          </span>
        ) : null}
        {item.contradictions.length > 0 ? (
          <span className="font-mono text-red-600 dark:text-red-400">
            conflict: {item.contradictions.join(", ")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function EvidencePanel({ report }: { report: ApiEvidenceReport }) {
  const byCategory = new Map<string, ApiEvidenceItem[]>();
  for (const item of report.evidence) {
    const group = byCategory.get(item.category) ?? [];
    group.push(item);
    byCategory.set(item.category, group);
  }

  return (
    <div className="space-y-4">
      {/* Strength summary */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {(
          [
            ["DIRECT", "info"],
            ["CORROBORATED", "success"],
            ["INDIRECT", "neutral"],
            ["MISSING", "warning"],
            ["CONTRADICTED", "danger"],
          ] as const
        ).map(([strength, tone]) => (
          <div
            key={strength}
            className={cn(
              "rounded-lg border px-3 py-2",
              tone === "success" &&
                "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/10",
              tone === "warning" &&
                "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10",
              tone === "danger" &&
                "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
              tone === "info" &&
                "border-blue-200 bg-blue-50/50 dark:border-blue-500/20 dark:bg-blue-500/10",
              tone === "neutral" &&
                "border-zinc-200 bg-zinc-50/50 dark:border-zinc-500/20 dark:bg-zinc-500/10"
            )}
          >
            <p className="text-lg font-semibold tabular-nums">
              {report.strength_summary[strength] ?? 0}
            </p>
            <p className="text-[10px] font-medium tracking-wide uppercase opacity-80">
              {strength}
            </p>
          </div>
        ))}
      </div>

      {/* Evidence gaps */}
      {report.gaps.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3 dark:border-amber-500/20 dark:bg-amber-500/5">
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            Evidence gaps
          </p>
          <ul className="space-y-1.5">
            {report.gaps.map((gap) => (
              <li key={`${gap.event_type}:${gap.rule_id}`} className="text-[11px]">
                <span className="font-mono font-medium text-foreground">
                  {gap.event_type}
                </span>
                <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                  {gap.rule_id}
                </span>
                <p className="mt-0.5 text-muted-foreground">{gap.note}</p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Structural observations only — a gap means the record was not
            observed, never that the transaction failed.
          </p>
        </div>
      )}

      {/* Contradictions */}
      {report.contradictions.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/40 p-3 dark:border-red-500/20 dark:bg-red-500/5">
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            Contradictions
          </p>
          <ul className="space-y-2">
            {report.contradictions.map((contradiction) => (
              <li key={contradiction.contradiction_id} className="text-[11px]">
                <p className="font-medium text-foreground">
                  {contradiction.type}{" "}
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {contradiction.rule_id}
                  </span>
                  <span className="ml-1.5 rounded border px-1 py-px text-[9px] font-medium uppercase">
                    {contradiction.severity}
                  </span>
                </p>
                <p className="mt-0.5 text-muted-foreground">
                  {contradiction.explanation}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                  {contradiction.event_ids.length} events ·{" "}
                  {contradiction.event_ids.map((id) => id.slice(0, 8)).join(" · ")}…
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Both sides are preserved — the engine records the conflict and
            never decides which event is correct.
          </p>
        </div>
      )}

      {/* Evidence items grouped by category */}
      {[...byCategory.entries()].map(([category, items]) => (
        <div key={category}>
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            {category.replace(/_/g, " ")}
          </p>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {items.map((item) => (
              <EvidenceCard key={item.evidence_id} item={item} />
            ))}
          </div>
        </div>
      ))}

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        The evidence engine reports what the records support — it does not
        determine the business outcome.
      </p>
    </div>
  );
}