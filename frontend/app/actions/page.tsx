import { ListChecks } from "lucide-react";

import type { ActionQueueItem, Tone } from "@/types/demo";
import { ACTION_QUEUE } from "@/lib/demo-data";
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
import { PageHeader } from "@/components/shared/page-header";
import { DemoTag } from "@/components/shared/demo-tag";
import { RiskBadge, StatusBadge } from "@/components/shared/status-badge";

export const metadata = {
  title: "Action Center",
};

const ACTION_STATUS_TONE: Record<ActionQueueItem["status"], Tone> = {
  queued: "neutral",
  in_review: "info",
  needs_approval: "warning",
  completed: "success",
};

export default function ActionsPage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Action Center"
        subtitle="Recommended actions on at-risk and failed outcomes — with human approval before execution."
        actions={<DemoTag />}
      />

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Action Queue</CardTitle>
          <CardDescription className="text-xs">
            Placeholder — recommendations arrive from the Decision Agent in
            later parts
          </CardDescription>
          <CardAction>
            <ListChecks className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Action</TableHead>
                <TableHead>Transaction</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Assigned To</TableHead>
                <TableHead className="pr-4 text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ACTION_QUEUE.map((action) => (
                <TableRow key={action.id}>
                  <TableCell className="pl-4">
                    <span className="text-xs font-medium text-foreground">
                      {action.kind}
                    </span>
                    <span className="block font-mono text-[10px] text-muted-foreground">
                      {action.id}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-foreground">
                    {action.transactionId}
                  </TableCell>
                  <TableCell>
                    <RiskBadge risk={action.priority} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={ACTION_STATUS_TONE[action.status]}>
                      {action.status.replace("_", " ")}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {action.assignedTo}
                  </TableCell>
                  <TableCell className="pr-4 text-right text-xs text-muted-foreground">
                    {formatDateTime(action.createdAt)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <p className="text-[11px] text-muted-foreground">
        No action is executed automatically. Every recommended action requires
        human approval before it touches money or customer communication.
      </p>
    </div>
  );
}