import { redirect } from "next/navigation";

import { ACTIVE_INVESTIGATIONS } from "@/lib/demo-data";

export const metadata = {
  title: "Investigation",
};

export default async function InvestigationCasePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // Every case URL resolves to the live investigation artifact: the full
  // deterministic pipeline (journey → evidence → consistency → outcome →
  // failure → impact → recommendation → approval) rendered on the matching
  // real transaction's detail page. Unknown ids fall back to the primary case.
  const row =
    ACTIVE_INVESTIGATIONS.find((case_) => case_.id === id) ??
    ACTIVE_INVESTIGATIONS[0];
  redirect(`/transactions/${row.transactionId}`);
}
