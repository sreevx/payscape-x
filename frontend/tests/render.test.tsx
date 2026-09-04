import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatusBadge } from "@/components/shared/status-badge";
import { PageHeader } from "@/components/shared/page-header";
import { DemoTag } from "@/components/shared/demo-tag";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { StatCard } from "@/components/shared/stat-card";

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

  it("renders a KPI stat card with a real value and no demo tag", () => {
    // Scope assertions to this card's container: other tests in this file
    // render DemoTag, so document-wide queries would see their output.
    const { container } = render(
      <StatCard
        kpi={{
          id: "kpi_payment_success",
          label: "Payment Success",
          value: "86.7%",
          tone: "info",
          description: "130 of 150 payments captured",
        }}
      />
    );
    expect(container.textContent).toContain("Payment Success");
    expect(container.textContent).toContain("86.7%");
    expect(container.textContent).toContain("130 of 150 payments captured");
    expect(container.textContent).not.toContain("DEMO DATA");
  });
});