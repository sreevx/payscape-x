import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Pipeline narrative strip — the PAYSCAPE-X analysis story at a glance:
 *
 *   PAYMENT → JOURNEY → EVIDENCE → CONSISTENCY → OUTCOME → FAILURE →
 *   IMPACT → SIMULATION → AI DECISION → HUMAN APPROVAL
 *
 * Each stage shows whether its engine produced data (done), failed to load
 * (error) or is still pending. The strip only reflects what actually
 * rendered below — it never fabricates a stage.
 */
export type PipelineStageStatus = "done" | "error" | "pending";

export interface PipelineStage {
  label: string;
  status: PipelineStageStatus;
  detail?: string;
}

const DOT_STYLES: Record<PipelineStageStatus, string> = {
  done: "bg-emerald-500",
  error: "bg-red-500",
  pending: "bg-zinc-400",
};

const PILL_STYLES: Record<PipelineStageStatus, string> = {
  done: "border-emerald-200 bg-emerald-50/60 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  error:
    "border-red-200 bg-red-50/60 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300",
  pending:
    "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-500/30 dark:bg-zinc-500/10 dark:text-zinc-400",
};

export function PipelineStrip({
  stages,
  caption,
}: {
  stages: PipelineStage[];
  caption?: string;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-y-2">
        {stages.map((stage, index) => (
          <div key={stage.label} className="flex items-center">
            {index > 0 ? (
              <ChevronRight
                className="mx-1 size-3 shrink-0 text-muted-foreground/50"
                aria-hidden
              />
            ) : null}
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
                PILL_STYLES[stage.status]
              )}
            >
              <span
                aria-hidden
                className={cn("size-1.5 rounded-full", DOT_STYLES[stage.status])}
              />
              {stage.label}
              {stage.detail ? (
                <span className="opacity-70">· {stage.detail}</span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
      {caption ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">{caption}</p>
      ) : null}
    </div>
  );
}