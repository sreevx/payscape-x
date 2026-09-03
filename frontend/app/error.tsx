"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/shared/states";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Logged server-side. Raw traces are never shown to the user.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <ErrorState
        title="This view could not be loaded"
        description="An unexpected error occurred. Your data is safe — please try again."
        onRetry={reset}
      />
    </div>
  );
}