import { cn } from "@/lib/utils";

/** Compact tag marking placeholder content as demo/synthetic data. */
export function DemoTag({ label = "DEMO DATA", className }: { label?: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border border-dashed border-zinc-300 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-zinc-500 uppercase dark:border-zinc-600 dark:text-zinc-400",
        className
      )}
    >
      {label}
    </span>
  );
}