import { Loader2 } from "lucide-react";

export function PageSpinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center gap-2 text-sm text-slate-500 dark:text-slate-400" role="status">
      <Loader2 className="size-5 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}
