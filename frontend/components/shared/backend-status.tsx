"use client";

import { RefreshCw } from "lucide-react";

import { useBackendHealth, type BackendConnectionState } from "@/hooks/use-backend-health";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const STATE_META: Record<
  BackendConnectionState,
  { label: string; dot: string; text: string }
> = {
  checking: {
    label: "Checking…",
    dot: "bg-amber-400",
    text: "text-zinc-600 dark:text-zinc-400",
  },
  connected: {
    label: "Backend Connected",
    dot: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-400",
  },
  unavailable: {
    label: "Backend Unavailable",
    dot: "bg-red-500",
    text: "text-red-700 dark:text-red-400",
  },
};

/**
 * Real backend connectivity indicator. It calls `GET /api/v1/health` and
 * reflects the actual result — nothing is faked. If the backend is down
 * the fallback state is displayed clearly.
 */
export function BackendStatus({ compact = false }: { compact?: boolean }) {
  const { state, refetch } = useBackendHealth();

  const meta = STATE_META[state];

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={() => void refetch()}
            aria-label="Backend status — click to re-check"
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-medium whitespace-nowrap transition-colors hover:bg-muted",
              meta.text
            )}
          >
            <span className="relative flex size-2" aria-hidden>
              {state === "checking" ? (
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-amber-400 opacity-60" />
              ) : null}
              <span className={cn("inline-flex size-2 rounded-full", meta.dot)} />
            </span>
            {compact ? null : <span>{meta.label}</span>}
            {state === "unavailable" && !compact ? (
              <RefreshCw className="size-3 opacity-60" aria-hidden />
            ) : null}
          </button>
        }
      />
      <TooltipContent>GET /api/v1/health — click to re-check</TooltipContent>
    </Tooltip>
  );
}