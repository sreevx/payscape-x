import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <p className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
        404
      </p>
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        The resource you are looking for does not exist or is not available in
        this part of the application.
      </p>
      <Link
        href="/dashboard"
        className="mt-2 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}