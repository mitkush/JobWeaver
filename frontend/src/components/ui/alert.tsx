import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const tones = {
  info: { icon: Info, cls: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-100" },
  success: { icon: CheckCircle2, cls: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100" },
  warning: { icon: AlertTriangle, cls: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-100" },
  error: { icon: XCircle, cls: "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/50 dark:text-red-100" },
};

export function Alert({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof tones;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const { icon: Icon, cls } = tones[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex gap-3 rounded-md border border-l-4 p-4 text-sm", cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex-1">
        {title && <p className="font-mono text-xs font-bold tracking-wider uppercase">{title}</p>}
        {children && <div className={cn(title && "mt-1")}>{children}</div>}
      </div>
      {action}
    </div>
  );
}
