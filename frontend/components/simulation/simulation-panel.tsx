import type {
  ApiSimulationBaseline,
  ApiSimulationCompareItem,
  ApiSimulationReport,
  ApiSimulationResult,
  ApiSimulationStatus,
} from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Simulation Lab panel (Part 7).
 *
 * Renders the deterministic, read-only counterfactual lab for one
 * transaction: the ACTUAL baseline, one card per intervention with its
 * SIMULATED result (or an honest NOT_APPLICABLE / NOT_EFFECTIVE /
 * NOT_SUPPORTED explanation), and the ranked comparison table. Every
 * counterfactual is labelled SIMULATED — a scenario estimate, never an
 * actual outcome, prediction or guarantee.
 */

const OUTCOME_TONES: Record<string, Tone> = {
  FULFILLED: "success",
  AT_RISK: "warning",
  FAILED: "danger",
  UNVERIFIABLE: "neutral",
};

const STATUS_TONES: Record<ApiSimulationStatus, Tone> = {
  SIMULATED: "warning",
  NOT_APPLICABLE: "neutral",
  NOT_EFFECTIVE: "neutral",
  NOT_SUPPORTED: "neutral",
};

const STATUS_HINTS: Record<ApiSimulationStatus, string> = {
  SIMULATED: "Deterministic scenario estimate over the observed records",
  NOT_APPLICABLE: "Not relevant to this transaction's records",
  NOT_EFFECTIVE: "Applicable in principle — deterministic prerequisites not met",
  NOT_SUPPORTED: "The dataset cannot support this action",
};

function BaselineBanner({ baseline }: { baseline: ApiSimulationBaseline }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-4 rounded-lg border p-4",
        baseline.outcome === "FULFILLED" &&
          "border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/20 dark:bg-emerald-500/5",
        baseline.outcome === "FAILED" &&
          "border-red-200 bg-red-50/40 dark:border-red-500/20 dark:bg-red-500/5",
        baseline.outcome === "AT_RISK" &&
          "border-amber-200 bg-amber-50/40 dark:border-amber-500/20 dark:bg-amber-500/5",
        baseline.outcome === "UNVERIFIABLE" &&
          "border-zinc-200 bg-zinc-50/40 dark:border-zinc-500/20 dark:bg-zinc-500/5"
      )}
    >
      <div className="flex flex-col items-start gap-1">
        <StatusBadge tone={OUTCOME_TONES[baseline.outcome] ?? "neutral"}>
          {baseline.outcome}
        </StatusBadge>
        <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Baseline outcome · actual records
        </p>
      </div>
      <div className="min-w-24">
        <p className="text-xl font-semibold tabular-nums">
          {Math.round(baseline.confidence * 100)}
          <span className="text-sm text-muted-foreground">%</span>
        </p>
        <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Confidence
        </p>
      </div>
      <div className="min-w-24">
        <p className="text-xl font-semibold tabular-nums">
          {Math.round(baseline.impact_score)}
          <span className="text-sm text-muted-foreground">/100</span>
        </p>
        <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Impact score
        </p>
      </div>
      <div className="flex flex-col items-start gap-1">
        <StatusBadge tone={OUTCOME_TONES[baseline.severity] ?? "neutral"}>
          {baseline.severity}
        </StatusBadge>
        <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Severity
        </p>
      </div>
      <div className="ml-auto max-w-64">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {baseline.root_causes.length > 0
            ? `Root cause: ${baseline.root_causes.map((root) => root.label).join(", ")}`
            : baseline.compound_failure_detected
              ? "Compound failure detected — see the failure chain above."
              : "No compound failure chain — the baseline is a non-failed or single-stage outcome."}
        </p>
        <p className="mt-1 font-mono text-[10px] text-muted-foreground/70">
          {baseline.event_ids.length} events · {baseline.evidence_ids.length} evidence
          items · {baseline.impact_scope}
        </p>
      </div>
    </div>
  );
}

function DeltaPill({ delta }: { delta: number }) {
  const improved = delta < 0;
  const worsened = delta > 0;
  return (
    <span
      className={cn(
        "rounded px-1.5 py-px font-mono text-[10px] font-semibold tabular-nums",
        improved && "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300",
        worsened && "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300",
        !improved && !worsened && "bg-muted text-muted-foreground"
      )}
    >
      {delta > 0 ? "+" : ""}
      {Math.round(delta * 10) / 10}
    </span>
  );
}

function RefList({
  title,
  refs,
  tone,
}: {
  title: string;
  refs: ApiSimulationResult["remaining_failures"];
  tone: "resolved" | "remaining";
}) {
  if (refs.length === 0) {
    return (
      <p className="text-[10px] text-muted-foreground">
        {title}: <span className="font-mono">none</span>
      </p>
    );
  }
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </p>
      <ul className="mt-1 space-y-0.5">
        {refs.map((ref) => (
          <li key={ref.kind} className="flex items-center gap-1.5 text-[10px]">
            <span
              aria-hidden
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                tone === "resolved" ? "bg-emerald-500/70" : "bg-red-500/70"
              )}
            />
            <span className="font-mono text-foreground/90">{ref.label}</span>
            <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">
              {ref.rule_id}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function InterventionCard({ item }: { item: ApiSimulationResult }) {
  const simulated = item.status === "SIMULATED";
  const outcomeTone = OUTCOME_TONES[item.simulated_outcome] ?? "neutral";
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        simulated
          ? "border-dashed border-amber-300 bg-amber-50/20 dark:border-amber-500/30 dark:bg-amber-500/5"
          : "border-zinc-200 bg-muted/15 dark:border-zinc-500/20"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs font-semibold text-foreground">
          {item.intervention.label}
        </span>
        {simulated ? (
          <StatusBadge tone="warning" className="text-[9px]">
            SIMULATED
          </StatusBadge>
        ) : (
          <StatusBadge tone={STATUS_TONES[item.status]} className="text-[9px]">
            {item.status}
          </StatusBadge>
        )}
        <span className="ml-auto font-mono text-[9px] text-muted-foreground/70">
          {item.intervention.intervention_type}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        {item.intervention.description}
      </p>

      <div className="mt-2 rounded-md border bg-background/60 p-2">
        <p className="text-[10px] leading-relaxed text-foreground/90">{item.reason}</p>
        {!simulated ? (
          <p className="mt-1 text-[10px] italic text-muted-foreground">
            {STATUS_HINTS[item.status]}
          </p>
        ) : null}
      </div>

      {/* Result metrics */}
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
        <div>
          <p className="text-[9px] font-medium tracking-wide text-muted-foreground uppercase">
            Simulated outcome
          </p>
          <p className="mt-0.5 flex items-center gap-1.5">
            <StatusBadge tone={outcomeTone} className="text-[9px]">
              {item.simulated_outcome}
            </StatusBadge>
          </p>
        </div>
        <div>
          <p className="text-[9px] font-medium tracking-wide text-muted-foreground uppercase">
            Impact delta
          </p>
          <p className="mt-0.5">
            <DeltaPill delta={item.delta_impact_score} />
          </p>
        </div>
        <div>
          <p className="text-[9px] font-medium tracking-wide text-muted-foreground uppercase">
            Impact {Math.round(item.baseline_impact_score)} →{" "}
            {Math.round(item.simulated_impact_score)}
          </p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            {item.simulated_outcome === item.baseline_outcome
              ? "no outcome change"
              : "outcome changes under this scenario"}
          </p>
        </div>
      </div>

      {/* Resolved / remaining */}
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <RefList title="Resolved failures" refs={item.resolved_failures} tone="resolved" />
        <RefList title="Remaining failures" refs={item.remaining_failures} tone="remaining" />
      </div>

      {/* Assumptions */}
      {item.assumptions.length > 0 && (
        <details className="mt-2 rounded-md border bg-muted/10 p-2">
          <summary className="cursor-pointer text-[10px] font-semibold tracking-wide uppercase">
            Assumptions ({item.assumptions.length})
          </summary>
          <ul className="mt-1.5 space-y-1">
            {item.assumptions.map((assumption, index) => (
              <li key={`${item.simulation_id}:${index}`} className="text-[10px] leading-relaxed text-muted-foreground">
                · {assumption}
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className="mt-2 font-mono text-[9px] text-muted-foreground/60">
        {item.rule_ids.length} rules · {item.event_ids.length} events ·{" "}
        {item.evidence_ids.length} evidence · id {item.simulation_id.slice(0, 8)}…
      </p>
    </div>
  );
}

function ComparisonTable({ rows }: { rows: ApiSimulationCompareItem[] }) {
  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-3 text-[11px] text-muted-foreground">
        No interventions are applicable — there is nothing to compare.
      </p>
    );
  }
  const best = rows[0];
  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-left">
          <thead className="bg-muted/30 text-[9px] tracking-wide text-muted-foreground uppercase">
            <tr>
              <th className="px-2 py-1.5">#</th>
              <th className="px-2 py-1.5">Intervention</th>
              <th className="px-2 py-1.5">Simulated outcome</th>
              <th className="px-2 py-1.5 text-right">Impact</th>
              <th className="px-2 py-1.5 text-right">Delta</th>
              <th className="px-2 py-1.5 text-right">Remaining failures</th>
            </tr>
          </thead>
          <tbody className="text-[11px]">
            {rows.map((row) => (
              <tr
                key={row.intervention_type}
                className={cn(
                  "border-t",
                  row.rank === best.rank && "bg-emerald-50/30 dark:bg-emerald-500/5"
                )}
              >
                <td className="px-2 py-1.5 font-mono text-muted-foreground">{row.rank}</td>
                <td className="px-2 py-1.5 font-medium text-foreground">{row.label}</td>
                <td className="px-2 py-1.5">
                  <StatusBadge
                    tone={OUTCOME_TONES[row.simulated_outcome] ?? "neutral"}
                    className="text-[9px]"
                  >
                    {row.simulated_outcome}
                  </StatusBadge>
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                  {Math.round(row.simulated_impact_score)}
                </td>
                <td className="px-2 py-1.5 text-right">
                  <DeltaPill delta={row.delta_impact_score} />
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                  {row.remaining_failure_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Ranked by simulated impact delta, then fewer remaining failures, then
        fewer assumptions. Lowest simulated impact is highlighted as the{" "}
        <span className="font-medium text-foreground">best simulated result</span>{" "}
        — the lab compares, it does not recommend.
      </p>
    </div>
  );
}

export function SimulationPanel({ report }: { report: ApiSimulationReport }) {
  const interventionCount = report.interventions.filter(
    (item) => item.status === "SIMULATED"
  ).length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone="warning" className="text-[9px]">
          BASELINE = ACTUAL RECORDS
        </StatusBadge>
        <StatusBadge tone="neutral" className="text-[9px]">
          {interventionCount} SIMULATED · {report.interventions.length} INTERVENTIONS
        </StatusBadge>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          deterministic · read-only · no AI · no predictions
        </span>
      </div>

      <BaselineBanner baseline={report.baseline} />

      {/* Intervention cards */}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
          Intervention cards
        </p>
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {report.interventions.map((item) => (
            <InterventionCard key={item.simulation_id} item={item} />
          ))}
        </div>
      </div>

      {/* Comparison */}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
          Comparison — best simulated result
        </p>
        <ComparisonTable rows={report.comparison} />
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Simulation results are deterministic scenario estimates, not
        predictions or guarantees. The lab never modifies payments, orders,
        inventory, refunds or webhooks.
      </p>
    </div>
  );
}
