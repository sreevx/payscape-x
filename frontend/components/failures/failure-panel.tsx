import type { ApiCompoundFailure } from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * Compound Failure panel (Part 6).
 *
 * Renders the deterministic compound-failure analysis: detected / not
 * detected, severity, the failure chain with OBSERVED|DERIVED labels,
 * deterministic edges and root cause(s). Everything traces back to event /
 * evidence ids — no predictions, no AI reasoning.
 */

const SEVERITY_TONES: Record<ApiCompoundFailure["severity"], Tone> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "neutral",
};

const RELATIONSHIP_LABEL: Record<string, string> = {
  CAUSES: "causes",
  BLOCKS: "blocks",
  LEADS_TO: "leads to",
  PREVENTS: "prevents",
  IMPACTS: "impacts",
};

function StatusChip({
  status,
  tone,
}: {
  status: "OBSERVED" | "DERIVED" | "POTENTIAL";
  tone: Tone;
}) {
  return (
    <StatusBadge tone={tone} className="text-[9px]">
      {status}
    </StatusBadge>
  );
}

function NodeCard({
  node,
  last,
  edge,
}: {
  node: ApiCompoundFailure["failure_chain"][number];
  last: boolean;
  edge?: ApiCompoundFailure["edges"][number];
}) {
  return (
    <div className="relative">
      <div
        className={cn(
          "rounded-lg border p-3",
          node.status === "OBSERVED"
            ? "border-red-200 bg-red-50/40 dark:border-red-500/25 dark:bg-red-500/5"
            : "border-sky-200 bg-sky-50/40 dark:border-sky-500/25 dark:bg-sky-500/5"
        )}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-mono text-[11px] font-semibold text-foreground">
            {node.label}
          </span>
          <span className="rounded border px-1 py-px font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
            {node.stage}
          </span>
          {node.status === "OBSERVED" ? (
            <StatusChip status="OBSERVED" tone="danger" />
          ) : (
            <StatusChip status="DERIVED" tone="info" />
          )}
          <span className="ml-auto font-mono text-[9px] text-muted-foreground/70">
            {node.rule_id}
          </span>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          {node.message}
        </p>
        {node.event_ids.length > 0 ? (
          <p className="mt-1 font-mono text-[10px] text-muted-foreground/80">
            {node.event_ids.length} event{node.event_ids.length === 1 ? "" : "s"} ·{" "}
            {node.event_ids.length} supporting evidence
          </p>
        ) : null}
      </div>
      {!last && edge ? (
        <div className="flex items-center gap-2 py-1 pl-3">
          <span className="size-2 rounded-full bg-muted-foreground/40" aria-hidden />
          <span className="font-mono text-[10px] font-medium text-muted-foreground uppercase">
            {RELATIONSHIP_LABEL[edge.relationship_type] ?? "leads to"}
          </span>
          <span className="text-[10px] text-muted-foreground/70">{edge.reason}</span>
          <span className="ml-auto font-mono text-[9px] text-muted-foreground/50">
            {edge.rule_id}
          </span>
        </div>
      ) : null}
    </div>
  );
}

export function FailurePanel({ failure }: { failure: ApiCompoundFailure }) {
  const chain = failure.failure_chain;

  if (!failure.detected) {
    const note =
      typeof failure.metadata?.note === "string"
        ? (failure.metadata.note as string)
        : "";
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-muted/20 p-3 dark:border-zinc-500/20">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="neutral">NOT DETECTED</StatusBadge>
            <span className="font-mono text-[11px] text-muted-foreground">
              {failure.reason}
            </span>
          </div>
          {note ? (
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
              {note}
            </p>
          ) : null}
        </div>
        {chain.length > 0 ? (
          <div>
            <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
              Single-stage business failure records
            </p>
            <p className="mb-2 text-[11px] text-muted-foreground">
              The journey failed at one stage only — not a compound chain.
            </p>
            <div className="space-y-0">
              {chain.map((node, index) => (
                <NodeCard
                  key={node.node_id}
                  node={node}
                  last={index === chain.length - 1}
                />
              ))}
            </div>
          </div>
        ) : null}
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
          The engine only reports a compound failure when several related
          problems form a connected chain across the promise stages.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-4 rounded-lg border p-4",
          failure.severity === "CRITICAL" &&
            "border-red-300 bg-red-50/60 dark:border-red-500/30 dark:bg-red-500/10",
          failure.severity === "HIGH" &&
            "border-red-200 bg-red-50/40 dark:border-red-500/20 dark:bg-red-500/5",
          failure.severity === "MEDIUM" &&
            "border-amber-200 bg-amber-50/40 dark:border-amber-500/20 dark:bg-amber-500/5"
        )}
      >
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={SEVERITY_TONES[failure.severity]} className="px-3 py-1 text-sm">
            {failure.severity}
          </StatusBadge>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Compound failure severity
          </p>
        </div>
        <div className="flex flex-col items-start gap-1">
          <StatusBadge
            tone={failure.classification === "OBSERVED" ? "success" : "info"}
          >
            {failure.classification}
          </StatusBadge>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Evidence classification
          </p>
        </div>
        <div className="min-w-24">
          <p className="text-xl font-semibold tabular-nums">
            {failure.failure_chain.length}
          </p>
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Chain stages
          </p>
        </div>
        {failure.confidence !== null ? (
          <div className="min-w-24">
            <p className="text-xl font-semibold tabular-nums">
              {Math.round(failure.confidence * 100)}
              <span className="text-sm text-muted-foreground">%</span>
            </p>
            <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              Confidence
            </p>
          </div>
        ) : null}
        <p className="w-full text-[11px] leading-relaxed text-muted-foreground">
          {failure.reason === "MULTI_STAGE_FAILURE_CHAIN"
            ? "Several related failures form a connected chain across the promise stages (payment → order → inventory → fulfillment → delivery → customer)."
            : failure.reason}
        </p>
      </div>

      {/* Failure chain */}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
          Failure chain
        </p>
        <div className="space-y-0">
          {chain.map((node, index) => (
            <NodeCard
              key={node.node_id}
              node={node}
              last={index === chain.length - 1}
              edge={failure.edges[index]}
            />
          ))}
        </div>
      </div>

      {/* Root causes */}
      {failure.root_causes.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wide uppercase">
            Root cause{failure.root_causes.length > 1 ? "s" : ""}
          </p>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {failure.root_causes.map((root) => (
              <div
                key={root.root_cause_id}
                className="rounded-lg border border-red-200 bg-red-50/40 p-3 dark:border-red-500/20 dark:bg-red-500/5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px] font-semibold">
                    {root.label}
                  </span>
                  <span className="rounded border px-1 py-px font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
                    {root.stage}
                  </span>
                  <span className="ml-auto font-mono text-[9px] text-muted-foreground/70">
                    {root.rule_id}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  {root.explanation}
                </p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground/80">
                  {root.event_ids.length} event
                  {root.event_ids.length === 1 ? "" : "s"} ·{" "}
                  {root.evidence_ids.length} evidence item
                  {root.evidence_ids.length === 1 ? "" : "s"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Chain nodes and edges are deterministic — each carries the rule that
        produced it. OBSERVED records are stated by the journey; DERIVED
        steps follow from documented absences. No event was modified.
      </p>
    </div>
  );
}
