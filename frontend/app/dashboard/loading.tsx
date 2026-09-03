import { LoadingState } from "@/components/shared/states";

export default function DashboardLoading() {
  return (
    <div className="space-y-4">
      <div className="h-10 w-72 animate-pulse rounded-md bg-muted" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="h-80 animate-pulse rounded-xl bg-muted lg:col-span-5" />
        <div className="h-80 animate-pulse rounded-xl bg-muted lg:col-span-7" />
      </div>
      <LoadingState rows={2} />
    </div>
  );
}