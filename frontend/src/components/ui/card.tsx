import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      // A stable hook for tests and scripts, independent of styling.
      data-card=""
      className={cn(
        "rounded-md border border-slate-200 bg-white/90 shadow-sm backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/75 dark:shadow-[inset_0_1px_0_rgb(255_255_255/0.04)]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4 dark:border-slate-800">
      <div>
        <h2 className="font-display text-base font-bold tracking-wide uppercase">{title}</h2>
        {description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 py-5", className)} {...props} />;
}
