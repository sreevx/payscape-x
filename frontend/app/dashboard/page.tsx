import { ActiveInvestigations } from "@/components/dashboard/active-investigations";
import { FailurePatterns } from "@/components/dashboard/failure-patterns";
import { KpiGrid } from "@/components/dashboard/kpi-grid";
import { OutcomeDistribution } from "@/components/dashboard/outcome-distribution";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { PageHeader } from "@/components/shared/page-header";
import { PipelineOverview } from "@/components/shared/pipeline-overview";
import { DemoTag } from "@/components/shared/demo-tag";

export const metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Payment Outcome Intelligence"
        subtitle="Monitor whether successful payments actually achieve their intended business outcomes."
        actions={<DemoTag />}
      />

      <KpiGrid />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <OutcomeDistribution />
        </div>
        <div className="lg:col-span-7">
          <ActiveInvestigations />
        </div>
      </div>

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