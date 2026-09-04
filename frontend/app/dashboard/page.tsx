import { ActiveInvestigations } from "@/components/dashboard/active-investigations";
import { DashboardSummary } from "@/components/dashboard/dashboard-summary";
import { FailurePatterns } from "@/components/dashboard/failure-patterns";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { PageHeader } from "@/components/shared/page-header";
import { PipelineOverview } from "@/components/shared/pipeline-overview";

export const metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Payment Outcome Intelligence"
        subtitle="Monitor whether successful payments actually achieve their intended business outcomes."
      />

      <DashboardSummary>
        <ActiveInvestigations />
      </DashboardSummary>

      <FailurePatterns />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <RecentActivity />
        </div>
        <div className="lg:col-span-7">
          <PipelineOverview />
        </div>
      </div>
    </div>
  );
}
