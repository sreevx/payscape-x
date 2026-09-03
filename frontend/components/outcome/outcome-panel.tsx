import type { ApiOutcome, ApiOutcomeReason } from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Outcome panel (Part 5).
 *
 * Renders the deterministic business-outcome classification: outcome state,
 * confidence, primary reason, corroborating reasons and traceability back
 * to evidence/event ids. The four states are visually distinct. This is a
 * business outcome — a successful payment does NOT imply FULFILLED.
 */

const OUTCOME_TONES: Record<ApiOutcome["outcome"], Tone> = {
  FULFILLED: "success",
  AT_RISK: "warning",
  FAILED: "danger",
  UNVERIFIABLE: "neutral",
};

const OUTCOME_NOTES: Record<ApiOutcome["outcome"], string> = {
  FULFILLED:
    "The observed records show the business transaction completed: the order was delivered.",
  AT_RISK:
    "The transaction may still complete, but the observed records show an unresolved problem.",
  FAILED:
    "The observed records show the business transaction did not and will not complete.",
  UNVERIFIABLE:
    "The records are insufficient or contradictory — the engine reports what it cannot verify rather than guessing.",
};

const SEVERITY_TONES: Record<string, Tone> = {
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "neutral",
};

function ReasonRow({ reason }: { reason: ApiOutcomeReason }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-[11px] font-semibold text-foreground">
          {reason.code}
        </span>
        <StatusBadge tone={SEVERITY_TONES[reason.severity] ?? "neutral"}>
          {reason.severity}
        </StatusBadge>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {reason.rule_id}
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
        {reason.message}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground/80">
        {reason.event_ids.length > 0 ? (
          <span className="font-mono">
            {reason.event_ids.length} event{reason.event_ids.length === 1 ? "" : "s"} ·{" "}
            {reason.event_ids.slice(0, 2).map((id) => id.slice(0, 8)).join(" · ")}…
          </span>
        ) : null}
        {reason.evidence_ids.length > 0 ? (
          <span className="font-mono">
            {reason.evidence_ids.length} evidence item
            {reason.evidence_ids.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function shortIds(ids: string[], max = 3): string {
  if (ids.length === 0) return "—";
  const shown = ids.slice(0, max).map((id) => id.slice(0, 8)).join(" · ");
  return ids.length > max ? `${shown} … (+${ids.length - max})` : shown;
}

export function OutcomePanel({ outcome }: { outcome: ApiOutcome }) {
  const tone = OUTCOME_TONES[outcome.outcome];
  const appliedRules = outcome.rule_trace.filter((step) => step.applied);

  return (
    <div className="space-y-4">
      {/* Outcome banner */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-4 rounded-lg border p-4",
          outcome.outcome === "FULFILLED" &&
            "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/10",
          outcome.outcome === "AT_RISK" &&
            "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10",
          outcome.outcome === "FAILED" &&
            "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
          outcome.outcome === "UNVERIFIABLE" &&
            "border-zinc-200 bg-zinc-50/50 dark:border-zinc-500/20 dark:bg-zinc-500/10"
        )}
      >
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={tone} className="px-3 py-1 text-sm">
            {outcome.outcome}
          </StatusBadge>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Business outcome
          </p>
        </div>
        <div className="min-w-32">
          <p className="text-2xl font-semibold tabular-nums">
            {Math.round(outcome.confidence * 100)}
            <span className="text-sm text-muted-foreground">%</span>
          </p>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Confidence
          </p>
        </div>
        <p className="w-full text-[11px] leading-relaxed text-muted-foreground">
          {OUTCOME_NOTES[outcome.outcome]}
        </p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(
          [
            ["Primary reason", outcome.primary_reason.code],
            ["Reasons", outcome.reasons.length],
            [
              "Evidence completeness",
              outcome.evidence_completeness === null
                ? "n/a"
                : `${Math.round(outcome.evidence_completeness * 100)}%`,
            ],
            ["Consistency", outcome.consistency_status ?? "—"],
          ] as const
        ).map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border bg-muted/20 px-3 py-2"
          >
            <p className="font-mono text-sm font-semibold break-all tabular-nums">
              {value}
            </p>
            <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              {label}
            </p>
          </div>
        ))}
      </div>

      {/* Primary reason */}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
          Primary reason
        </p>
        <ReasonRow reason={outcome.primary_reason} />
      </div>

      {/* Corroborating reasons */}
      {outcome.reasons.length > 1 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            Corroborating reasons
          </p>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {outcome.reasons.slice(1).map((reason) => (
              <ReasonRow key={reason.code} reason={reason} />
            ))}
          </div>
        </div>
      )}

      {/* Traceability */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-lg border bg-muted/20 p-3">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Supporting evidence
          </p>
          <p className="mt-1 font-mono text-[11px] break-all">
            {shortIds(outcome.supporting_evidence_ids)}
          </p>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Supporting events
          </p>
          <p className="mt-1 font-mono text-[11px] break-all">
            {shortIds(outcome.supporting_event_ids)}
          </p>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Blocking evidence
          </p>
          <p className="mt-1 font-mono text-[11px] break-all">
            {outcome.blocking_evidence_ids.length === 0
              ? "none"
              : shortIds(outcome.blocking_evidence_ids)}
          </p>
        </div>
      </div>

      {/* Confidence adjustments */}
      {outcome.confidence_adjustments.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3 dark:border-amber-500/20 dark:bg-amber-500/5">
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            Confidence adjustments
          </p>
          <ul className="space-y-1.5">
            {outcome.confidence_adjustments.map((adjustment, index) => (
              <li
                key={`${adjustment.signal}:${index}`}
                className="text-[11px]"
              >
                <span className="font-mono font-medium text-foreground">
                  {adjustment.signal} {adjustment.delta}
                </span>
                <span className="ml-2 text-muted-foreground">
                  {adjustment.note}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Rule trace */}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
          Rule trace — {appliedRules.length} of {outcome.rule_trace.length} fired
        </p>
        <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
          {outcome.rule_trace.map((step) => (
            <div
              key={step.rule_id}
              className={cn(
                "rounded-md border p-2 text-[11px] leading-relaxed",
                step.applied
                  ? "border-blue-200 bg-blue-50/40 dark:border-blue-500/20 dark:bg-blue-500/5"
                  : "border-zinc-200 bg-muted/20 dark:border-zinc-500/20"
              )}
            >
              <p className="font-mono font-medium text-foreground">
                {step.rule_id}
                <span className="ml-1.5 text-[10px] text-muted-foreground">
                  #{step.priority}
                </span>
                {step.applied ? (
                  <span className="ml-1.5 rounded border border-blue-300 px-1 py-px text-[9px] font-semibold text-blue-700 dark:border-blue-500/40 dark:text-blue-400">
                    FIRED
                  </span>
                ) : null}
              </p>
              <p className="mt-0.5 text-muted-foreground">{step.note}</p>
            </div>
          ))}
        </div>
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Deterministic classification over the journey, evidence and
        consistency records — a successful payment does not imply a fulfilled
        business transaction.
      </p>
    </div>
  );
}