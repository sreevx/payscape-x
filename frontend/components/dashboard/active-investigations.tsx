import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { ACTIVE_INVESTIGATIONS } from "@/lib/demo-data";
import { formatDateTime } from "@/lib/format";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { OutcomeBadge, PaymentStatusBadge, RiskBadge } from "@/components/shared/status-badge";

export function ActiveInvestigations() {
  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Active Investigations</CardTitle>
        <CardDescription className="text-xs">
          Cases where a successful payment may not have achieved its outcome
        </CardDescription>
        <CardAction>
          <Link
            href="/investigation"
            className="inline-flex items-center gap-0.5 text-xs font-medium text-foreground hover:underline"
          >
            View all <ArrowUpRight className="size-3" aria-hidden />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Transaction</TableHead>
              <TableHead>Payment Status</TableHead>
              <TableHead>Business Outcome</TableHead>
              <TableHead>Risk</TableHead>
              <TableHead>Last Event</TableHead>
              <TableHead className="pr-4 text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ACTIVE_INVESTIGATIONS.map((investigation) => (
              <TableRow key={investigation.id}>
                <TableCell className="pl-4">
                  <Link
                    href={`/transactions/${investigation.transactionId}`}
                    className="font-mono text-xs text-foreground hover:underline"
                  >
                    {investigation.transactionId}
                  </Link>
                </TableCell>
                <TableCell>
                  <PaymentStatusBadge status={investigation.paymentStatus} />
                </TableCell>
                <TableCell>
                  <OutcomeBadge outcome={investigation.outcome} />
                </TableCell>
                <TableCell>
                  <RiskBadge risk={investigation.risk} />
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {investigation.lastEvent}
                </TableCell>
                <TableCell className="pr-4 text-right text-xs text-muted-foreground">
                  {formatDateTime(investigation.updatedAt)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}