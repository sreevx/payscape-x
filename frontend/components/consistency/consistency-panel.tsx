import type { ApiConsistencyCheck, ApiConsistencyResult } from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Consistency panel (Part 4).
 *
 * Renders the deterministic rule evaluation: PASS / VIOLATION /
 * INSUFFICIENT EVIDENCE / NOT APPLICABLE per rule, with severity and a
 * deterministic explanation. overall_integrity reflects record agreement
 * only — FULFILLED / AT RISK / FAILED belong to Part 5 and are never shown.
 */

const STATUS_TONES: Record<ApiConsistencyCheck["status"], Tone> = {
  PASS: "success",
  VIOLATION: "danger",
  INSUFFICIENT_EVIDENCE: "warning",
  NOT_APPLICABLE: "neutral",
};

const SEVERITY_TONES: Record<string, Tone> = {
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "neutral",
};

const INTEGRITY_TONES: Record<ApiConsistencyResult["overall_integrity"], Tone> = {
  CONSISTENT: "success",
  INCONSISTENT: "danger",
  INSUFFICIENT_EVIDENCE: "warning",
};

const INTEGRITY_NOTE: Record<ApiConsistencyResult["overall_integrity"], string> = {
  CONSISTENT:
    "The observed records agree with each other. This is record agreement — not a business outcome.",
  INCONSISTENT:
    "At least one rule found records that disagree. Both sides are preserved; nothing is resolved or deleted.",
  INSUFFICIENT_EVIDENCE:
    "No rule could be verified: the records present neither agree nor disagree. Absence of evidence is not evidence of failure.",
};

function CheckRow({ check }: { check: ApiConsistencyCheck }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusBadge tone={STATUS_TONES[check.status]}>
          {check.status === "INSUFFICIENT_EVIDENCE" ? "INSUFFICIENT EVIDENCE" : check.status}
        </StatusBadge>
        <span className="text-xs font-medium text-foreground">{check.name}</span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {check.rule_id}
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
        {check.explanation}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground/80">
        <span>
          severity{" "}
          <StatusBadge tone={SEVERITY_TONES[check.severity] ?? "neutral"}>
            {check.severity}
          </StatusBadge>
        </span>
        {check.supporting_event_ids.length > 0 ? (
          <span className="font-mono">
            {check.supporting_event_ids.length} event
            {check.supporting_event_ids.length === 1 ? "" : "s"} ·{" "}
            {check.supporting_event_ids[0].slice(0, 8)}…
          </span>
        ) : (
          <span>no supporting events</span>
        )}
      </div>
    </div>
  );
}

export function ConsistencyPanel({
  result,
}: {
  result: ApiConsistencyResult;
}) {
  const integrityTone = INTEGRITY_TONES[result.overall_integrity];

  return (
    <div className="space-y-4">
      {/* Overall integrity banner */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-3 rounded-lg border p-4",
          result.overall_integrity === "CONSISTENT" &&
            "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/10",
          result.overall_integrity === "INCONSISTENT" &&
            "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
          result.overall_integrity === "INSUFFICIENT_EVIDENCE" &&
            "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10"
        )}
      >
        <div className="flex items-center gap-2">
          <StatusBadge tone={integrityTone}>
            {result.overall_integrity.replace(/_/g, " ")}
          </StatusBadge>
          <span className="text-xs font-semibold tracking-wide uppercase">
            Overall integrity
          </span>
        </div>
        <p className="w-full text-[11px] leading-relaxed text-muted-foreground">
          {INTEGRITY_NOTE[result.overall_integrity]}
        </p>
      </div>

      {/* Per-status counts */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(
          [
            ["PASS", result.passed.length, "success"],
            ["VIOLATION", result.violations.length, "danger"],
            ["INSUFFICIENT EVIDENCE", result.insufficient_evidence.length, "warning"],
            ["NOT APPLICABLE", result.not_applicable.length, "neutral"],
          ] as const
        ).map(([label, value, tone]) => (
          <div
            key={label}
            className={cn(
              "rounded-lg border px-3 py-2",
              tone === "success" &&
                "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/10",
              tone === "danger" &&
                "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
              tone === "warning" &&
                "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10",
              tone === "neutral" &&
                "border-zinc-200 bg-zinc-50/50 dark:border-zinc-500/20 dark:bg-zinc-500/10"
            )}
          >
            <p className="text-lg font-semibold tabular-nums">{value}</p>
            <p className="text-[10px] font-medium tracking-wide uppercase opacity-80">
              {label}
            </p>
          </div>
        ))}
      </div>

      {/* Rule checks */}
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {result.checks.map((check) => (
          <CheckRow key={check.rule_id} check={check} />
        ))}
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        The consistency engine checks whether observed records agree — it does
        not determine the business outcome.
      </p>
    </div>
  );
}