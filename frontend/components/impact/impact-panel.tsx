import Link from "next/link";
import type { ApiConsequence, ApiImpact } from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Consequences / Impact panel (Part 6).
 *
 * Renders the deterministic consequence analysis with a strict visual
 * separation: OBSERVED facts (solid), DERIVED steps (dashed), POTENTIAL
 * possible futures (outlined — never presented as facts). Also shows
 * single vs multi-transaction scope, the affected cohort and the
 * transparent impact score.
 */

const SEVERITY_TONES: Record<ApiImpact["severity"], Tone> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "neutral",
};

const SCOPE_TONES: Record<ApiImpact["scope"], Tone> = {
  SINGLE_TRANSACTION: "neutral",
  MULTI_TRANSACTION: "warning",
};

function ConsequenceRow({
  item,
  classification,
}: {
  item: ApiConsequence;
  classification: ApiConsequence["classification"];
}) {
  const isObserved = classification === "OBSERVED";
  const isDerived = classification === "DERIVED";
  const isPotential = classification === "POTENTIAL";
  return (
    <div
      className={cn(
        "rounded-lg border p-2.5 text-[11px] leading-relaxed",
        isObserved &&
          "border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/25 dark:bg-emerald-500/5",
        isDerived &&
          "border-sky-200 bg-sky-50/30 dark:border-sky-500/25 dark:bg-sky-500/5",
        isPotential &&
          "border-dashed border-amber-300 bg-amber-50/30 dark:border-amber-500/30 dark:bg-amber-500/5"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className={cn(
            "rounded px-1.5 py-px text-[9px] font-semibold tracking-wide uppercase",
            isObserved && "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300",
            isDerived && "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300",
            isPotential && "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
          )}
        >
          {item.classification}
        </span>
        <span className="rounded border px-1 py-px font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
          {item.category}
        </span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground/70">
          {item.rule_id}
        </span>
      </div>
      <p className="mt-1 text-foreground/90">{item.claim}</p>
      {isPotential ? (
        <p className="mt-0.5 text-[10px] italic text-muted-foreground">
          Possible future state signalled by the records — not an observed fact.
        </p>
      ) : null}
      {item.event_ids.length > 0 ? (
        <p className="mt-1 font-mono text-[9px] text-muted-foreground/80">
          {item.event_ids.length} event{item.event_ids.length === 1 ? "" : "s"} ·{" "}
          {item.evidence_ids.length} evidence
        </p>
      ) : null}
    </div>
  );
}

function ConsequenceGroup({
  title,
  items,
  emptyNote,
}: {
  title: string;
  items: ApiConsequence[];
  emptyNote: string;
}) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold tracking-wide uppercase">{title}</p>
      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed p-2.5 text-[11px] text-muted-foreground">
          {emptyNote}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
          {items.map((item) => (
            <ConsequenceRow key={item.consequence_id} item={item} classification={item.classification} />
          ))}
        </div>
      )}
    </div>
  );
}

function shortIds(ids: string[], max = 2): string {
  if (ids.length === 0) return "—";
  return ids
    .slice(0, max)
    .map((id) => id.slice(0, 8))
    .join(" · ");
}

export function ImpactPanel({ impact }: { impact: ApiImpact }) {
  const multi = impact.scope === "MULTI_TRANSACTION";

  return (
    <div className="space-y-4">
      {/* Header metrics */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-4 rounded-lg border p-4",
          impact.severity === "CRITICAL" &&
            "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
          impact.severity === "HIGH" &&
            "border-orange-200 bg-orange-50/40 dark:border-orange-500/20 dark:bg-orange-500/10",
          impact.severity === "MEDIUM" &&
            "border-amber-200 bg-amber-50/40 dark:border-amber-500/20 dark:bg-amber-500/5",
          impact.severity === "LOW" && "border-zinc-200 bg-muted/20"
        )}
      >
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={SEVERITY_TONES[impact.severity]} className="px-3 py-1 text-sm">
            {impact.severity}
          </StatusBadge>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Impact severity
          </p>
        </div>
        <div className="min-w-28">
          <p className="text-2xl font-semibold tabular-nums">
            {Math.round(impact.impact_score)}
            <span className="text-sm text-muted-foreground">/100</span>
          </p>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Impact score
          </p>
        </div>
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={SCOPE_TONES[impact.scope]}>{impact.scope}</StatusBadge>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Scope
          </p>
        </div>
        <div className="ml-auto flex flex-col items-end gap-1 text-right">
          <p className="font-mono text-sm font-semibold tabular-nums">
            {impact.affected_transactions} tx · {impact.affected_orders} orders ·{" "}
            {impact.affected_products} product{impact.affected_products === 1 ? "" : "s"}
          </p>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Affected
          </p>
        </div>
      </div>

      {multi ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3 dark:border-amber-500/20 dark:bg-amber-500/5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <StatusBadge tone="warning">SHARED FAILURE</StatusBadge>
            <span className="text-[11px] text-muted-foreground">
              The same stock shortage hit other orders:{" "}
              <span className="font-mono text-foreground">
                {impact.shared_skus.join(", ")}
              </span>
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {impact.shared_failure_patterns.join(" · ")} — this failure is not
            isolated to one transaction.
          </p>
        </div>
      ) : null}

      <ConsequenceGroup
        title="Observed consequences"
        items={impact.observed_consequences}
        emptyNote="No observed consequences — no record states a downstream effect."
      />
      <ConsequenceGroup
        title="Derived consequences"
        items={impact.derived_consequences}
        emptyNote="No derived consequences — nothing follows deterministically from the records."
      />
      <ConsequenceGroup
        title="Potential consequences"
        items={impact.potential_consequences}
        emptyNote="No potential consequences — the records signal no unresolved future risk."
      />

      {/* Affected cohort (multi-transaction) */}
      {multi && impact.affected.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold tracking-wide uppercase">
            Other affected transactions ({impact.affected.length})
          </p>
          <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-2">
            {impact.affected.map((member) => (
              <Link
                key={member.transaction_id}
                href={`/transactions/${member.transaction_id}`}
                className="rounded-lg border bg-muted/20 p-2.5 transition-colors hover:border-foreground/30"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="font-mono text-[10px] font-semibold">
                    {member.external_order_id || member.transaction_id.slice(0, 8)}
                  </span>
                  <StatusBadge
                    tone={
                      member.outcome === "FAILED"
                        ? "danger"
                        : member.outcome === "AT_RISK"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {member.outcome ?? "—"}
                  </StatusBadge>
                  <span className="ml-auto font-mono text-[9px] text-muted-foreground/80">
                    {member.scenario_slug}
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-[9px] text-muted-foreground/80">
                  {member.product_skus.join(", ") || "—"} · impact {member.impact}
                </p>
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {/* Score methodology */}
      <details className="group rounded-lg border bg-muted/20 p-3">
        <summary className="cursor-pointer text-[11px] font-semibold tracking-wide uppercase">
          Impact score methodology ({impact.score_components.length} components)
        </summary>
        <ul className="mt-2 space-y-1">
          {impact.score_components.map((component, index) => (
            <li key={`${component.signal}:${index}`} className="flex gap-2 text-[10px]">
              <span className="w-44 shrink-0 font-mono text-muted-foreground">
                {component.signal}
              </span>
              <span className="w-10 shrink-0 text-right font-mono tabular-nums">
                {component.points}
              </span>
              <span className="text-muted-foreground">{component.note}</span>
            </li>
          ))}
        </ul>
      </details>

      {impact.observed_consequences.length + impact.derived_consequences.length +
        impact.potential_consequences.length > 0 ? (
        <p className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
          {impact.event_ids.length} events · {impact.evidence_ids.length} evidence
          items · ids {shortIds(impact.event_ids)}
        </p>
      ) : null}

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        OBSERVED facts come from records; DERIVED steps follow deterministically;
        POTENTIAL states are signalled possibilities — never presented as facts.
        The impact score is a transparent deterministic index, not a financial
        loss estimate and not a prediction.
      </p>
    </div>
  );
}
