import { BrandMark } from "./brand";

export function LoadingMark({ compact = false }: { compact?: boolean }) {
  return <span className={compact ? "loading-mark loading-mark-small" : "loading-mark"} aria-hidden="true"><BrandMark className={compact ? "size-4" : "size-7"} /></span>;
}

export function PageSpinner({ label = "Loading" }: { label?: string }) {
  return <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-sm text-slate-600 dark:text-slate-400" role="status"><LoadingMark /><span>{label}</span></div>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400" role="status"><LoadingMark compact />{label}</span>;
}

/** Decorative placeholders keep the Feed's responsive columns and one loading announcement. */
export function FeedSkeleton() {
  return <div role="status" aria-label="Loading your feed" aria-busy="true">
    <span className="sr-only">Loading your feed</span>
    <div className="grid gap-4 xl:grid-cols-2" aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => <div key={index} className="space-y-5 rounded-md border border-slate-200 bg-white/80 p-5 dark:border-slate-800 dark:bg-slate-900/75">
        <div className="skeleton-line h-5 w-3/4" /><div className="skeleton-line h-3 w-1/3" />
        <div className="flex gap-2"><div className="skeleton-line h-5 w-20" /><div className="skeleton-line h-5 w-28" /></div>
        <div className="space-y-2"><div className="skeleton-line h-3 w-full" /><div className="skeleton-line h-3 w-4/5" /></div>
        <div className="skeleton-line h-8 w-32" />
      </div>)}
    </div>
  </div>;
}
