import { redirect } from "next/navigation";

import { ACTIVE_INVESTIGATIONS } from "@/lib/demo-data";

export default function InvestigationsPage() {
  // Landing target for the sidebar entry — opens the most recent case.
  // A full case-list route arrives with the investigation workspace.
  const first = ACTIVE_INVESTIGATIONS[0];
  redirect(first ? `/investigation/${first.id}` : "/dashboard");
}