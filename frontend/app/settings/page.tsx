import { Database, Globe, ShieldCheck, UsersRound } from "lucide-react";

import { DEMO_MODE, DEMO_MODE_LABEL } from "@/lib/demo-mode";
import { API_BASE_URL } from "@/lib/api-client";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { PageHeader } from "@/components/shared/page-header";
import { BackendStatus } from "@/components/shared/backend-status";
import { StatusBadge } from "@/components/shared/status-badge";

export const metadata = {
  title: "Settings",
};

export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader
        title="Settings"
        subtitle="Workspace, connectivity and demo configuration."
      />

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">General</CardTitle>
          <CardDescription className="text-xs">
            Workspace identity
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="workspace" className="text-[11px] font-medium text-muted-foreground">
              Workspace name
            </label>
            <Input id="workspace" defaultValue="PAYSCAPE-X" disabled />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="timezone" className="text-[11px] font-medium text-muted-foreground">
              Timezone
            </label>
            <Input id="timezone" defaultValue="Asia/Kolkata (UTC+5:30)" disabled />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <div>
                <p className="text-xs font-medium text-foreground">Demo Mode</p>
                <p className="text-[11px] text-muted-foreground">
                  Synthetic data layer — disabled automatically once the real
                  event pipeline is connected
                </p>
              </div>
              <StatusBadge tone={DEMO_MODE ? "warning" : "neutral"}>
                {DEMO_MODE ? DEMO_MODE_LABEL : "OFF"}
              </StatusBadge>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">API &amp; Connectivity</CardTitle>
          <CardDescription className="text-xs">
            The frontend talks to the FastAPI backend through a typed client
          </CardDescription>
          <CardAction>
            <Globe className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2">
            <div className="min-w-0">
              <p className="text-xs font-medium text-foreground">Backend status</p>
              <p className="truncate font-mono text-[11px] text-muted-foreground">
                GET {API_BASE_URL}/api/v1/health
              </p>
            </div>
            <BackendStatus />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="api-url" className="text-[11px] font-medium text-muted-foreground">
              API base URL (NEXT_PUBLIC_API_BASE_URL)
            </label>
            <Input id="api-url" defaultValue={API_BASE_URL} disabled />
          </div>
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
            No secrets are exposed to the browser. Credentials live only in
            environment variables on the backend.
          </p>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Demo Data</CardTitle>
          <CardDescription className="text-xs">
            Where synthetic values come from in this part
          </CardDescription>
          <CardAction>
            <Database className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-muted-foreground">
          <p>
            All dashboard KPIs, transactions, investigations, failure patterns
            and events are seeded from a dedicated mock data layer
            (<code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">frontend/lib/demo-data.ts</code>).
            No business logic lives inside components (Rule 8).
          </p>
          <p>
            In later parts this layer is replaced by structured events from the
            backend synthetic pipeline.
          </p>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle className="text-sm">Team</CardTitle>
          <CardDescription className="text-xs">
            Placeholder — access control arrives with the operator workspace
          </CardDescription>
          <CardAction>
            <UsersRound className="size-4 text-muted-foreground" aria-hidden />
          </CardAction>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <div>
              <p className="text-xs font-medium text-foreground">
                Operations Analyst
              </p>
              <p className="text-[11px] text-muted-foreground">
                operator@payscape-x.local · Risk Operations
              </p>
            </div>
            <StatusBadge tone="neutral">Owner</StatusBadge>
          </div>
          <Separator className="my-3" />
          <p className="text-[11px] text-muted-foreground">
            Role-based access, approval flows and audit trails arrive with the
            Decision Agent and Human Approval modules.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}