import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Scale, SearchCheck, ShieldCheck } from "lucide-react";

import { getInvestigationCase, getTransactionDetail } from "@/lib/demo-data";
import { formatDateTime } from "@/lib/format";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DemoTag } from "@/components/shared/demo-tag";
import {
  OutcomeBadge,
  PaymentStatusBadge,
  RiskBadge,
  StatusBadge,
} from "@/components/shared/status-badge";

export const metadata = {
  title: "Investigation",
};

const STAGES = [
  { name: "Evidence Gathering", description: "Collect and validate structured events", ready: false },
  { name: "Consistency Engine", description: "Cross-check events against the journey", ready: false },
  { name: "Outcome Engine", description: "Classify FULFILLED / AT_RISK / FAILED / UNVERIFIABLE", ready: false },
  { name: "Simulation", description: "Stress-test counterfactual scenarios", ready: false },
  { name: "Human Approval", description: "Review and approve recommended actions", ready: false },
];

export default async function InvestigationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const case_ = getInvestigationCase(id);

  if (!case_) {
    notFound();
  }

  const detail = getTransactionDetail(case_.transactionId);
  const tx = detail?.transaction;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <Link
        href="/dashboard"
        className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3" aria-hidden /> Dashboard
      </Link>

      {/* Case header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <SearchCheck className="size-4 text-muted-foreground" aria-hidden />
            <h1 className="text-lg font-semibold tracking-tight">{case_.title}</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Case {case_.id} · opened {formatDateTime(case_.openedAt)} · owned by{" "}
            {case_.owner}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <StatusBadge tone="info">{case_.stage}</StatusBadge>
            <StatusBadge
              tone={
                case_.priority === "high"
                  ? "danger"
                  : case_.priority === "medium"
                    ? "warning"
                    : "neutral"
              }
            >
              {case_.priority} priority
            </StatusBadge>
            {tx ? (
              <>
                <PaymentStatusBadge status={tx.paymentStatus} />
                <OutcomeBadge outcome={tx.outcome} />
                <RiskBadge risk={tx.risk} />
              </>
            ) : null}
          </div>
        </div>
        <DemoTag />
      </div>

      {tx ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-sm">Transaction under review</CardTitle>
            <CardDescription className="text-xs">
              A successful payment whose intended business outcome is in question
            </CardDescription>
            <CardAction>
              <Link
                href={`/transactions/${tx.id}`}
                className="inline-flex items-center gap-1 text-xs font-medium hover:underline"
              >
                View transaction →
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
            <div>
              <p className="text-[11px] text-muted-foreground">Transaction</p>
              <p className="mt-0.5 font-mono">{tx.id}</p>
            </div>
            <div>
              <p className="text-[11px] text-muted-foreground">Order</p>
              <p className="mt-0.5 font-mono">{tx.orderId}</p>
            </div>
            <div>
              <p className="text-[11px] text-muted-foreground">Customer</p>
              <p className="mt-0.5">{tx.customerName}</p>
            </div>
            <div>
              <p className="text-[11px] text-muted-foreground">Last event</p>
              <p className="mt-0.5 font-mono">{tx.lastEvent}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Case summary + evidence */}
        <div className="space-y-4 lg:col-span-7">
          <Card size="sm">
            <CardHeader>
              <CardTitle className="text-sm">Case Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {case_.summary}
              </p>
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader>
              <CardTitle className="text-sm">Evidence</CardTitle>
              <CardDescription className="text-xs">
                Structured events attached to this case — collected by the
                Evidence Engine in a later part
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {case_.evidence.map((item, index) => (
                <div
                  key={index}
                  className="flex items-start gap-2 rounded-md border px-2.5 py-1.5"
                >
                  <ShieldCheck
                    className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                  <span className="font-mono text-[11px] text-foreground">
                    {item}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Future pipeline stages (disabled placeholders) */}
        <div className="lg:col-span-5">
          <Card size="sm" className="h-full">
            <CardHeader>
              <CardTitle className="text-sm">Investigation Pipeline</CardTitle>
              <CardDescription className="text-xs">
                Stages arrive in later parts — nothing here is simulated
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {STAGES.map((stage) => (
                <div
                  key={stage.name}
                  className="flex items-center justify-between gap-2 rounded-lg border border-dashed px-3 py-2.5"
                >
                  <div className="flex items-center gap-2.5">
                    <Scale className="size-3.5 text-muted-foreground" aria-hidden />
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        {stage.name}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {stage.description}
                      </p>
                    </div>
                  </div>
                  <Badge variant="outline" className="shrink-0">
                    Part 3
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}