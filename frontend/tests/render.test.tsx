import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatusBadge } from "@/components/shared/status-badge";
import { PageHeader } from "@/components/shared/page-header";
import { DemoTag } from "@/components/shared/demo-tag";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { StatCard } from "@/components/shared/stat-card";
import { KPI_SUMMARY } from "@/lib/demo-data";

describe("shared components render", () => {
  it("renders a StatusBadge with its tone and label", () => {
    render(<StatusBadge tone="success">FULFILLED</StatusBadge>);
    const badge = screen.getByText("FULFILLED");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("emerald");
  });

  it("renders a PageHeader with title and subtitle", () => {
    render(
      <PageHeader
        title="Payment Outcome Intelligence"
        subtitle="Monitor whether successful payments achieve outcomes."
      />
    );
    expect(
      screen.getByRole("heading", { name: "Payment Outcome Intelligence" })
    ).toBeInTheDocument();
    expect(
      screen.getByText("Monitor whether successful payments achieve outcomes.")
    ).toBeInTheDocument();
  });

  it("renders the demo data tag", () => {
    render(<DemoTag />);
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(<EmptyState title="No transactions" />);
    expect(screen.getByText("No transactions")).toBeInTheDocument();
  });

  it("renders an error state without exposing stack traces", () => {
    render(<ErrorState title="Failed to load" description="Try again." />);
    expect(screen.getByText("Failed to load")).toBeInTheDocument();
    expect(screen.queryByText(/at .*\.tsx:\d+/)).not.toBeInTheDocument();
  });

  it("renders a KPI stat card from demo data", () => {
    const kpi = KPI_SUMMARY.find((item) => item.id === "kpi_payment_success");
    if (!kpi) throw new Error("demo KPI missing");
    render(<StatCard kpi={kpi} />);
    expect(screen.getByText("Payment Success")).toBeInTheDocument();
    expect(screen.getByText("98.4%")).toBeInTheDocument();
    expect(screen.getAllByText("DEMO DATA").length).toBeGreaterThan(0);
  });
});