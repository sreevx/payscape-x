import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  BrainCircuit,
  ChevronDown,
  CreditCard,
  Gauge,
  Route,
} from "lucide-react";

import {
  ApiError,
  getCompoundFailure,
  getConsistency,
  getDecision,
  getEvidence,
  getImpact,
  getJourney,
  getOutcome,
  getSimulations,
  getTransaction,
} from "@/lib/api-client";
import { JourneyGraph } from "@/components/journey/journey-graph";
import { JourneyIntegrity } from "@/components/journey/journey-integrity";
import { EvidencePanel } from "@/components/evidence/evidence-panel";
import { ConsistencyPanel } from "@/components/consistency/consistency-panel";
import { OutcomePanel } from "@/components/outcome/outcome-panel";
import { ImpactPanel } from "@/components/impact/impact-panel";
import { SimulationPanel } from "@/components/simulation/simulation-panel";
import { DecisionPanel } from "@/components/decision/decision-panel";
import { formatCurrency, formatDateTime } from "@/lib/format";
import {
  displayOutcome,
  journeyMilestones,
  outcomeHeadline,
} from "@/lib/journey-summary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "@/components/shared/status-badge";
import { PipelineStrip } from "@/components/shared/pipeline-strip";
import { ErrorState } from "@/components/shared/states";
import { cn } from "@/lib/utils";
import type { ApiOutcome, ApiTransactionDetail } from "@/types/api";
import type { Tone } from "@/types/demo";

export const metadata = {
  title: "Transaction",
};

export const dynamic = "force-dynamic";

/** Presentational mapping from backend payment status to a state tone. */
const PAYMENT_STATUS_TONES: Record<string, Tone> = {
  CREATED: "neutral",
  AUTHORIZED: "info",
  CAPTURED: "success",
  FAILED: "danger",
  REFUNDED: "info",
  PARTIALLY_REFUNDED: "warning",
};

const ORDER_STATUS_TONES: Record<string, Tone> = {
  CREATED: "neutral",
  PAYMENT_PENDING: "warning",
  CONFIRMED: "info",
  FULFILLING: "info",
  SHIPPED: "info",
  DELIVERED: "success",
  CANCELLED: "danger",
  REFUNDED: "info",
};

const OUTCOME_TONES: Record<ApiOutcome["outcome"], Tone> = {
  FULFILLED: "success",
  AT_RISK: "warning",
  FAILED: "danger",
  UNVERIFIABLE: "neutral",
};

const HERO_STYLES: Record<ApiOutcome["outcome"], string> = {
  FULFILLED:
    "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/10",
  AT_RISK:
    "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10",
  FAILED:
    "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/10",
  UNVERIFIABLE:
    "border-zinc-200 bg-zinc-50/50 dark:border-zinc-500/20 dark:bg-zinc-500/10",
};

const MILESTONE_DOT: Record<"reached" | "blocked" | "pending", string> = {
  reached: "bg-emerald-500",
  blocked: "bg-red-500",
  pending: "bg-zinc-400",
};

/** Compact payload summary: a few key/value pairs, truncated. */
function payloadSummary(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).slice(0, 4);
  if (entries.length === 0) return "no payload";
  return entries
    .map(([key, value]) => `${key}=${String(value).slice(0, 40)}`)
    .join(" · ");
}

/** Numbered narrative step: the primary story reads top to bottom. */
function NarrativeStep({
  number,
  title,
  icon: Icon,
  children,
}: {
  number: number;
  title: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  children: React.ReactNode;
}) {
  return (
    <Card size="sm">
      <CardContent className="gap-3">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-[11px] font-bold text-background"
          >
            {number}
          </span>
          <Icon className="size-4 text-muted-foreground" aria-hidden />
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

/** Advanced-details expandable: technical records below the narrative. */
function AdvancedSection({
  summary,
  children,
  defaultOpen = false,
}: {
  summary: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="group rounded-lg border bg-background/40" open={defaultOpen}>
      <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2.5 text-xs font-medium text-foreground select-none">
        {summary}
        <ChevronDown
          className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="border-t px-3 py-3">{children}</div>
    </details>
  );
}

export default async function TransactionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let detail;
  let journey;
  let evidence;
  let consistency;
  let outcome;
  let failure;
  let impact;
  let simulation;
  let decision;
  try {
    [detail, journey, evidence, consistency, outcome, failure, impact, simulation, decision] =
      await Promise.all([
        getTransaction(id),
        getJourney(id),
        getEvidence(id),
        getConsistency(id),
        getOutcome(id),
        getCompoundFailure(id),
        getImpact(id),
        getSimulations(id),
        getDecision(id),
      ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <Card size="sm">
          <ErrorState
            title="Backend unavailable"
            description="The transaction API is unreachable. Start the backend and seed the database, then try again."
          />
        </Card>
      </div>
    );
  }

  const milestones = journeyMilestones(detail.events);
  const paymentTone = PAYMENT_STATUS_TONES[detail.payment_status] ?? "neutral";
  const orderTone = ORDER_STATUS_TONES[detail.order_status] ?? "neutral";

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <Link
        href="/transactions"
        className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3" aria-hidden /> Transactions
      </Link>

      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-lg font-semibold tracking-tight">
              {detail.id}
            </h1>
            <StatusBadge tone={paymentTone}>{detail.payment_status}</StatusBadge>
            <StatusBadge tone={orderTone}>ORDER {detail.order_status}</StatusBadge>
            {detail.scenario_type ? (
              <StatusBadge tone="neutral">{detail.scenario_type}</StatusBadge>
            ) : null}
          </div>
          <p className="text-sm text-muted-foreground">
            {detail.external_order_id} · {detail.customer_name} ·{" "}
            {detail.merchant_name}
          </p>
        </div>
      </div>

      {/* Pipeline narrative — the PAYSCAPE-X analysis story at a glance */}
      <Card size="sm">
        <CardContent className="gap-2">
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            From payment success to business outcome
          </p>
          <PipelineStrip
            stages={[
              { label: "PAYMENT", status: "done", detail: detail.payment_status },
              { label: "JOURNEY", status: journey ? "done" : "pending" },
              { label: "EVIDENCE", status: evidence ? "done" : "pending" },
              { label: "CONSISTENCY", status: consistency ? "done" : "pending" },
              {
                label: "OUTCOME",
                status: outcome ? "done" : "pending",
                detail: outcome?.outcome,
              },
              { label: "FAILURE", status: failure ? "done" : "pending" },
              { label: "IMPACT", status: impact ? "done" : "pending" },
              { label: "SIMULATION", status: simulation ? "done" : "pending" },
              {
                label: "AI DECISION",
                status: decision ? "done" : "pending",
                detail: decision?.recommended_action,
              },
              {
                label: "HUMAN APPROVAL",
                status: decision ? "done" : "pending",
                detail: decision?.approval_status,
              },
            ]}
            caption="A successful payment does not necessarily mean a successful business transaction. Each engine below is deterministic — AI reasons, code verifies, and the human stays in control."
          />
        </CardContent>
      </Card>

      {/* STEP 0 — OUTCOME (the strongest visual element) */}
      {outcome ? (
        <OutcomeHero detail={detail} outcome={outcome} />
      ) : (
        <Card size="sm">
          <ErrorState
            title="Outcome unavailable"
            description="The outcome API could not be reached."
          />
        </Card>
      )}

      {/* STEP 1 — PAYMENT */}
      <NarrativeStep number={1} title="Payment" icon={CreditCard}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: "Amount", value: formatCurrency(detail.amount, detail.currency) },
            { label: "Provider", value: detail.provider },
            { label: "Method", value: detail.method ?? "—" },
            { label: "Status", value: detail.payment_status },
            {
              label: "Captured at",
              value: detail.captured_at ? formatDateTime(detail.captured_at) : "—",
            },
            { label: "Order", value: detail.external_order_id },
            { label: "Customer", value: detail.customer_name },
            { label: "Merchant", value: detail.merchant_name },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border bg-muted/20 px-3 py-2">
              <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {item.label}
              </p>
              <p className="mt-0.5 font-mono text-xs font-semibold break-all tabular-nums">
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </NarrativeStep>

      {/* STEP 2 — WHAT HAPPENED */}
      <NarrativeStep number={2} title="What Happened" icon={Route}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {milestones.map((milestone) => (
            <div key={milestone.key} className="rounded-lg border bg-muted/20 px-3 py-2">
              <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <span
                  aria-hidden
                  className={cn("size-2 shrink-0 rounded-full", MILESTONE_DOT[milestone.state])}
                />
                {milestone.label}
              </p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">
                {milestone.note}
              </p>
            </div>
          ))}
        </div>
        {detail.scenario_description ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {detail.scenario_description}
          </p>
        ) : null}
      </NarrativeStep>

      {/* STEP 3 — WHY */}
      <NarrativeStep number={3} title="Why" icon={AlertCircle}>
        <div className="space-y-3">
          {outcome ? (
            <div className="rounded-lg border bg-muted/20 p-3">
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Primary reason
              </p>
              <p className="mt-1 text-xs leading-relaxed text-foreground/90">
                {outcome.primary_reason.message}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                <span className="font-mono">{outcome.primary_reason.code}</span>
                <span>·</span>
                <span>Consistency: {outcome.consistency_status ?? "—"}</span>
                <span>·</span>
                <span>
                  Evidence completeness:{" "}
                  {outcome.evidence_completeness === null
                    ? "n/a"
                    : `${Math.round(outcome.evidence_completeness * 100)}%`}
                </span>
              </div>
            </div>
          ) : null}

          {outcome && outcome.reasons.length > 1 ? (
            <div className="rounded-lg border bg-muted/20 p-3">
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Additional reasons
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {outcome.reasons.slice(1).map((reason) => (
                  <li key={reason.code} className="text-[11px] leading-relaxed">
                    <span className="font-mono font-medium text-foreground">
                      {reason.code}
                    </span>
                    <span className="ml-2 text-muted-foreground">{reason.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {failure && failure.detected && failure.root_causes.length > 0 ? (
            <div className="rounded-lg border border-red-200 bg-red-50/40 p-3 dark:border-red-500/20 dark:bg-red-500/5">
              <p className="text-[10px] font-semibold tracking-wide text-red-700 uppercase dark:text-red-300">
                Root cause{failure.root_causes.length === 1 ? "" : "s"}
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {failure.root_causes.map((rootCause) => (
                  <li key={rootCause.root_cause_id} className="text-[11px] leading-relaxed">
                    <span className="font-medium text-foreground">{rootCause.label}</span>
                    <span className="ml-2 text-muted-foreground">
                      {rootCause.explanation}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </NarrativeStep>

      {/* STEP 4 — IMPACT */}
      <NarrativeStep number={4} title="Impact" icon={Gauge}>
        {impact ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ["Impact score", String(impact.impact_score)],
                ["Severity", impact.severity],
                ["Scope", impact.scope.replace("_", " ")],
                [
                  "Affected transactions",
                  String(impact.affected_transactions),
                ],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border bg-muted/20 px-3 py-2">
                  <p className="font-mono text-sm font-semibold break-all tabular-nums">
                    {value}
                  </p>
                  <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                    {label}
                  </p>
                </div>
              ))}
            </div>
            <ConsequenceSummary
              label="Observed"
              claims={impact.observed_consequences.map((c) => c.claim)}
            />
            <ConsequenceSummary
              label="Derived"
              claims={impact.derived_consequences.map((c) => c.claim)}
            />
            <ConsequenceSummary
              label="Potential — signalled, not a prediction"
              claims={impact.potential_consequences.map((c) => c.claim)}
            />
          </div>
        ) : (
          <ErrorState
            title="Impact analysis unavailable"
            description="The impact API could not be reached."
          />
        )}
      </NarrativeStep>

      {/* STEP 5 — WHAT SHOULD WE DO? */}
      <NarrativeStep number={5} title="What Should We Do?" icon={BrainCircuit}>
        {decision ? (
          <DecisionPanel decision={decision} />
        ) : (
          <ErrorState
            title="AI Decision unavailable"
            description="The decisions API could not be reached."
          />
        )}
      </NarrativeStep>

      {/* ADVANCED DETAILS — everything technical, kept below the story */}
      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Advanced details</CardTitle>
          <CardDescription className="text-xs">
            Evidence, consistency checks, engine internals and raw records —
            all deterministic and traceable, kept below the primary narrative
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {outcome ? (
            <AdvancedSection summary="View outcome details">
              <OutcomePanel outcome={outcome} />
            </AdvancedSection>
          ) : null}

          {evidence ? (
            <AdvancedSection summary="View evidence">
              <EvidencePanel report={evidence} />
            </AdvancedSection>
          ) : null}

          {consistency ? (
            <AdvancedSection summary="View consistency checks">
              <ConsistencyPanel result={consistency} />
            </AdvancedSection>
          ) : null}

          {journey ? (
            <AdvancedSection summary="View technical journey">
              <div className="space-y-4">
                <JourneyIntegrity integrity={journey.integrity} />
                <Separator />
                <JourneyGraph graph={journey.graph} journey={journey} />
              </div>
            </AdvancedSection>
          ) : null}

          <AdvancedSection summary={`View event details (${detail.events.length})`}>
            <ol className="space-y-0">
              {detail.events.map((event, index) => (
                <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
                  {index < detail.events.length - 1 ? (
                    <span
                      aria-hidden
                      className="absolute top-7 left-[7px] h-[calc(100%-1.75rem)] w-px bg-border"
                    />
                  ) : null}
                  <span
                    aria-hidden
                    className="z-10 mt-1.5 size-3.5 shrink-0 rounded-full border-2 border-foreground/40 bg-background"
                  />
                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-mono text-xs font-medium text-foreground">
                        {event.event_type}
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {formatDateTime(event.timestamp)}
                      </span>
                      <span className="text-[10px] text-muted-foreground/70 uppercase">
                        {event.source}
                      </span>
                    </div>
                    <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      {payloadSummary(event.payload)}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground/70">
                      correlation {event.correlation_id}
                      {event.idempotency_key
                        ? ` · idem ${event.idempotency_key}`
                        : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </AdvancedSection>

          {impact ? (
            <AdvancedSection summary="View impact details">
              <ImpactPanel impact={impact} />
            </AdvancedSection>
          ) : null}

          {simulation ? (
            <AdvancedSection summary="View simulation details">
              <SimulationPanel report={simulation} />
            </AdvancedSection>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

/** The strongest visual element: the business outcome in plain English. */
function OutcomeHero({
  detail,
  outcome,
}: {
  detail: ApiTransactionDetail;
  outcome: ApiOutcome;
}) {
  const tone = OUTCOME_TONES[outcome.outcome];
  const headline = outcomeHeadline(detail.payment_status, outcome.outcome);

  return (
    <div className={cn("rounded-xl border p-5", HERO_STYLES[outcome.outcome])}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
            Business outcome
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <span className="text-3xl font-bold tracking-tight text-foreground">
              {displayOutcome(outcome.outcome)}
            </span>
            <StatusBadge tone={tone} className="text-[10px]">
              {Math.round(outcome.confidence * 100)}% confidence
            </StatusBadge>
          </div>
          <p className="mt-2 max-w-2xl text-sm font-medium text-foreground">
            {headline}
          </p>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
            {outcome.primary_reason.message}
          </p>
        </div>
        <div className="rounded-lg border bg-background/70 px-3 py-2 text-right">
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Scenario
          </p>
          <p className="mt-0.5 font-mono text-xs font-semibold text-foreground">
            {detail.scenario_slug ?? "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

/** A compact consequence summary (observed / derived / potential). */
function ConsequenceSummary({
  label,
  claims,
}: {
  label: string;
  claims: string[];
}) {
  if (claims.length === 0) return null;
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <ul className="mt-1.5 space-y-1">
        {claims.slice(0, 4).map((claim, index) => (
          <li key={`${label}:${index}`} className="text-[11px] leading-relaxed text-foreground/90">
            {claim}
          </li>
        ))}
        {claims.length > 4 ? (
          <li className="text-[10px] text-muted-foreground">
            +{claims.length - 4} more in advanced details
          </li>
        ) : null}
      </ul>
    </div>
  );
}