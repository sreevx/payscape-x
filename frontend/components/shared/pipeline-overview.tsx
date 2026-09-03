import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The PAYSCAPE-X pipeline at a glance — the simple visual explanation of
 * what the product does. Every stage is live and deterministic; the strip
 * is intentionally jargon-light (technical engines live below the surface).
 */

const PIPELINE: string[] = [
  "Payment",
  "Journey",
  "Evidence",
  "Consistency",
  "Outcome",
  "Failure & Impact",
  "Simulation",
  "AI Decision",
  "Human Approval",
];

export function PipelineOverview() {
  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">How PAYSCAPE-X works</CardTitle>
        <CardDescription className="text-xs">
          From payment success to business outcome — every stage is
          deterministic, and the human stays in control
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-wrap items-center gap-1.5">
          {PIPELINE.map((step, index) => (
            <li key={step} className="flex items-center gap-1.5">
              <span className="rounded-md border border-zinc-300 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-foreground dark:border-zinc-600 dark:bg-zinc-800/60">
                {step}
              </span>
              {index < PIPELINE.length - 1 ? (
                <span className="text-zinc-300 dark:text-zinc-600" aria-hidden>
                  →
                </span>
              ) : null}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          PAYSCAPE-X reconstructs what happened, checks the evidence,
          determines the business outcome, identifies the failure and
          impact, simulates possible interventions — and lets AI recommend
          the next step while keeping a human in control. It never executes
          a financial action on its own.
        </p>
      </CardContent>
    </Card>
  );
}