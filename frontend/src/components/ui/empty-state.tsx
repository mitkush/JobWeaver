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
    <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 px-6 py-12 text-center dark:border-slate-700">
      <div className="rounded-full bg-brand-50 p-3 text-brand-600 dark:bg-brand-600/20 dark:text-brand-100">
        <Icon className="size-6" aria-hidden />
      </div>
      <h2 className="mt-4 text-base font-semibold">{title}</h2>
      {children && <div className="mt-2 max-w-md text-sm text-slate-600 dark:text-slate-400">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
