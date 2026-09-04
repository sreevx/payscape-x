import { ApiError, getTransactions } from "@/lib/api-client";
import { TransactionsTable } from "@/components/transactions/transactions-table";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState } from "@/components/shared/states";
import { Card } from "@/components/ui/card";

export const metadata = {
  title: "Transactions",
};

export const dynamic = "force-dynamic";

export default async function TransactionsPage() {
  let data;
  try {
    // First page at the API's max page size — the synthetic dataset is small
    // enough that a single page covers it; pagination arrives with the
    // ingestion pipeline in later parts.
    data = await getTransactions({ limit: 200 });
  } catch (error) {
    const unavailable =
      error instanceof ApiError && error.status !== 404
        ? "The transactions API is unreachable. Start the backend and seed the database with `python -m app.seed`."
        : "The transactions API could not be reached. Try again shortly.";
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <PageHeader
          title="Transactions"
          subtitle="Every payment flowing through the platform and its current business outcome."

        />
        <Card size="sm">
          <ErrorState title="Backend unavailable" description={unavailable} />
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Transactions"
        subtitle="Every payment flowing through the platform and its current business outcome."
      />
      <TransactionsTable
        transactions={data.items}
        total={data.total}
      />
    </div>
  );
}