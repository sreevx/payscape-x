"use client";

import { useState } from "react";
import { BrainCircuit, ShieldAlert, ThumbsDown, ThumbsUp } from "lucide-react";

import { ApiError, approveDecision, rejectDecision } from "@/lib/api-client";
import type { ApiDecision } from "@/types/api";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/status-badge";
import type { Tone } from "@/types/demo";

/**
 * AI Decision Agent panel (Part 8).
 *
 * Shows the auditable recommendation for one transaction: the closed
 * registry action, concise reason, deterministic confidence, evidence
 * chips, simulation basis and alternatives — plus the human-approval
 * workflow (PENDING -> APPROVED / REJECTED with an optional reason).
 *
 * Every interaction here only RECORDS the merchant's decision. The panel
 * never executes refunds, payments, messages or any external action, and
 * it clearly labels whether the recommendation came from the LLM or the
 * deterministic fallback.
 */

const ACTION_TONES: Record<string, Tone> = {
  DO_NOTHING: "neutral",
  RECOVER_ROOT_CAUSE: "info",
  REFUND_OR_CONTAIN: "warning",
  HUMAN_REVIEW: "danger",
};

const ACTION_HINTS: Record<string, string> = {
  DO_NOTHING: "No action is deterministically justified",
  RECOVER_ROOT_CAUSE: "Recover the recorded root cause",
  REFUND_OR_CONTAIN: "Contain customer impact — never fixes delivery",
  HUMAN_REVIEW: "Escalate to human operations",
};

const APPROVAL_TONES: Record<string, Tone> = {
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
};

function Confidence({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-xl font-semibold tabular-nums">
        {Math.round(value * 100)}
        <span className="text-sm text-muted-foreground">%</span>
      </p>
      <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
    </div>
  );
}

function ChipList({
  label,
  ids,
  limit = 8,
}: {
  label: string;
  ids: string[];
  limit?: number;
}) {
  if (ids.length === 0) {
    return (
      <p className="text-[10px] text-muted-foreground">
        {label}: <span className="font-mono">none referenced</span>
      </p>
    );
  }
  const shown = ids.slice(0, limit);
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
        {label} ({ids.length})
      </p>
      <div className="mt-1 flex flex-wrap gap-1">
        {shown.map((id) => (
          <span
            key={id}
            className="rounded border bg-background px-1.5 py-0.5 font-mono text-[9px] text-foreground/80"
          >
            {id.slice(0, 8)}…
          </span>
        ))}
        {ids.length > shown.length ? (
          <span className="px-1 py-0.5 text-[9px] text-muted-foreground">
            +{ids.length - shown.length} more
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function DecisionPanel({ decision }: { decision: ApiDecision }) {
  const [current, setCurrent] = useState<ApiDecision>(decision);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const pending = current.approval_status === "PENDING";
  const isLLM = current.decision_source === "LLM";

  const handleApprove = async () => {
    setBusy("approve");
    setActionError(null);
    try {
      setCurrent(await approveDecision(current.decision_id));
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? `Approval could not be recorded (HTTP ${error.status ?? "network"}).`
          : "Approval could not be recorded."
      );
    } finally {
      setBusy(null);
    }
  };

  const handleReject = async () => {
    setBusy("reject");
    setActionError(null);
    try {
      setCurrent(
        await rejectDecision(
          current.decision_id,
          rejectReason.trim() || undefined
        )
      );
      setRejecting(false);
      setRejectReason("");
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? `Rejection could not be recorded (HTTP ${error.status ?? "network"}).`
          : "Rejection could not be recorded."
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Source + safety labels */}
      <div className="flex flex-wrap items-center gap-2">
        {isLLM ? (
          <StatusBadge tone="info" className="text-[9px]">
            AI-GENERATED RECOMMENDATION
          </StatusBadge>
        ) : (
          <StatusBadge tone="neutral" className="text-[9px]">
            DETERMINISTIC FALLBACK
          </StatusBadge>
        )}
        <StatusBadge tone="neutral" className="text-[9px]">
          RECOMMENDATION ONLY — NEVER EXECUTES
        </StatusBadge>
        <StatusBadge tone={APPROVAL_TONES[current.approval_status] ?? "neutral"} className="text-[9px]">
          {current.approval_status}
        </StatusBadge>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {current.decision_id.slice(0, 8)}… · {isLLM ? "AI" : "CODE"}
        </span>
      </div>

      {/* Recommended action */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
        <div className="flex size-9 items-center justify-center rounded-md bg-muted">
          <BrainCircuit className="size-4 text-muted-foreground" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Recommended action
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold text-foreground">
              {current.recommended_action}
            </span>
            <StatusBadge
              tone={ACTION_TONES[current.recommended_action] ?? "neutral"}
              className="text-[9px]"
            >
              {ACTION_HINTS[current.recommended_action] ?? ""}
            </StatusBadge>
          </div>
        </div>
        <div className="flex gap-6">
          <Confidence label="Decision" value={current.decision_confidence} />
          <Confidence label="Evidence" value={current.evidence_confidence} />
        </div>
      </div>

      {/* Why */}
      <div className="rounded-lg border bg-muted/15 p-3">
        <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
          Why
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-foreground/90">
          {current.reason}
        </p>
      </div>

      {/* Evidence + simulation basis */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border bg-background/60 p-3">
          <ChipList label="Evidence" ids={current.evidence_ids} />
        </div>
        <div className="rounded-lg border bg-background/60 p-3">
          <ChipList label="Supporting events" ids={current.event_ids} limit={6} />
          <div className="mt-2 border-t pt-2">
            <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
              Simulation basis
            </p>
            <p className="mt-0.5 font-mono text-[10px] text-foreground/80">
              {current.simulation_id
                ? `${current.simulation_id.slice(0, 8)}… (SIMULATED)`
                : "none — baseline reference"}
            </p>
          </div>
        </div>
      </div>

      {/* Alternatives */}
      {current.alternatives.length > 0 && (
        <div className="rounded-lg border bg-background/60 p-3">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Alternatives
          </p>
          <ul className="mt-1.5 space-y-1">
            {current.alternatives.map((alternative) => (
              <li key={alternative.action} className="flex items-baseline gap-2 text-[10px]">
                <span className="font-mono text-foreground/90">
                  {alternative.action}
                </span>
                <span className="text-muted-foreground">{alternative.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Approval workflow */}
      <div className="rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="size-4 text-muted-foreground" aria-hidden />
            <p className="text-xs font-semibold text-foreground">Human approval</p>
          </div>
          <StatusBadge
            tone={APPROVAL_TONES[current.approval_status] ?? "neutral"}
            className="text-[9px]"
          >
            {current.approval_status}
          </StatusBadge>
          {current.human_approval_required ? (
            <span className="text-[10px] text-muted-foreground">
              This action requires a human decision before it could be executed
            </span>
          ) : (
            <span className="text-[10px] text-muted-foreground">
              No action to execute — approval not required
            </span>
          )}
        </div>

        {current.rejection_reason ? (
          <p className="mt-2 rounded-md bg-muted/30 p-2 text-[10px] text-muted-foreground">
            Rejection reason: <span className="text-foreground/90">{current.rejection_reason}</span>
          </p>
        ) : null}

        {actionError ? (
          <p className="mt-2 rounded-md bg-red-50 p-2 text-[10px] text-red-700 dark:bg-red-500/10 dark:text-red-300">
            {actionError}
          </p>
        ) : null}

        {pending && current.human_approval_required ? (
          <div className="mt-3 space-y-2">
            {rejecting ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  aria-label="Rejection reason"
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                  placeholder="Optional rejection reason…"
                  className="h-9 flex-1 rounded-lg border bg-background px-3 text-xs text-foreground outline-none focus:border-foreground/40"
                />
                <button
                  type="button"
                  onClick={() => void handleReject()}
                  disabled={busy !== null}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-red-600 px-3 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  <ThumbsDown className="size-3.5" aria-hidden /> Confirm reject
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRejecting(false);
                    setRejectReason("");
                  }}
                  disabled={busy !== null}
                  className="inline-flex h-9 items-center rounded-lg border px-3 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleApprove()}
                  disabled={busy !== null}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-600 px-3 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  <ThumbsUp className="size-3.5" aria-hidden />
                  {busy === "approve" ? "Recording…" : "Approve"}
                </button>
                <button
                  type="button"
                  onClick={() => setRejecting(true)}
                  disabled={busy !== null}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
                >
                  <ThumbsDown className="size-3.5" aria-hidden /> Reject
                </button>
              </div>
            )}
          </div>
        ) : null}
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span aria-hidden className="size-1.5 rounded-full bg-muted-foreground/50" />
        Approving or rejecting only records the merchant&apos;s decision. It
        never executes refunds, payments, messages or any external action.{" "}
        {current.decision_source === "DETERMINISTIC_FALLBACK" ? (
          <span className={cn("text-muted-foreground")}>
            The recommendation came from the deterministic fallback — no LLM
            was used.
          </span>
        ) : null}
      </p>
    </div>
  );
}