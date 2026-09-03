import type { BusinessOutcome, PaymentStatus, RiskLevel, Tone } from "@/types/demo";
import { cn } from "@/lib/utils";

/**
 * Semantic status badge. Color is used strictly to communicate state:
 * success / warning / danger / info / neutral.
 */

const TONE_STYLES: Record<Tone, string> = {
  success:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400",
  warning:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400",
  danger:
    "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400",
  info: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-400",
  neutral:
    "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-500/30 dark:bg-zinc-500/10 dark:text-zinc-400",
};

export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        TONE_STYLES[tone],
        className
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

const OUTCOME_TONES: Record<BusinessOutcome, Tone> = {
  FULFILLED: "success",
  AT_RISK: "warning",
  FAILED: "danger",
  UNVERIFIABLE: "neutral",
};

export function OutcomeBadge({ outcome }: { outcome: BusinessOutcome }) {
  return <StatusBadge tone={OUTCOME_TONES[outcome]}>{outcome}</StatusBadge>;
}

const PAYMENT_TONES: Record<PaymentStatus, Tone> = {
  succeeded: "success",
  failed: "danger",
  pending: "warning",
  refunded: "info",
  disputed: "danger",
};

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return <StatusBadge tone={PAYMENT_TONES[status]}>{status}</StatusBadge>;
}

const RISK_TONES: Record<RiskLevel, Tone> = {
  low: "neutral",
  medium: "warning",
  high: "warning",
  critical: "danger",
};

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  return (
    <StatusBadge tone={RISK_TONES[risk]} className="uppercase">
      {risk}
    </StatusBadge>
  );
}