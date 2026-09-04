import { redirect } from "next/navigation";

import { ACTIVE_INVESTIGATIONS } from "@/lib/demo-data";

export const metadata = {
  title: "Investigations",
};

export default function InvestigationsPage() {
  // Landing target for the sidebar entry. The investigation artifact in
  // PAYSCAPE-X is the live deterministic pipeline rendered on a real
  // transaction's detail page — open the most recent FAILED case directly.
  const target = ACTIVE_INVESTIGATIONS[0];
  redirect(target ? `/transactions/${target.transactionId}` : "/dashboard");
}
