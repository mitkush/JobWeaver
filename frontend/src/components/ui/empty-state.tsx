import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Empty screens always say what to do next (UX rule 4). */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-md border border-dashed border-slate-300 bg-white/40 px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-950/40">
      <div className="clip-corner bg-brand-50 p-3 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
        <Icon className="size-6" aria-hidden />
      </div>
      <h2 className="mt-4 font-display text-base font-bold tracking-wide uppercase">{title}</h2>
      {children && <div className="mt-2 max-w-md text-sm text-slate-600 dark:text-slate-400">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
