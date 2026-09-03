import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/** Generic loading state (skeleton shimmer). */
export function LoadingState({
  rows = 4,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="h-10 animate-pulse rounded-md bg-muted"
        />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

/** Generic empty state — used when a dataset has no rows. */
export function EmptyState({
  title = "Nothing here yet",
  description,
  className,
}: {
  title?: string;
  description?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center",
        className
      )}
    >
      <Inbox className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-sm text-xs text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

/**
 * Generic error state. Deliberately hides technical detail — raw stack
 * traces must never be shown to users; they belong in server logs only.
 */
export function ErrorState({
  title = "Something went wrong",
  description = "The request could not be completed. Please try again.",
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-red-200 bg-red-50/40 px-6 py-10 text-center dark:border-red-500/30 dark:bg-red-500/5",
        className
      )}
    >
      <AlertCircle className="size-6 text-red-600 dark:text-red-400" aria-hidden />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs text-muted-foreground">{description}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted"
        >
          <Loader2 className="size-3" aria-hidden /> Retry
        </button>
      ) : null}
    </div>
  );
}