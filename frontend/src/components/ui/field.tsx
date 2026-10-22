import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const control =
  "w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/25 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950/80 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-accent-400 dark:focus:ring-accent-400/20";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(control, "h-10", className)} {...props} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(control, "min-h-24 py-2", className)} {...props} />;
  },
);

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(control, "h-10", className)} {...props} />;
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block font-mono text-xs font-bold tracking-wider text-slate-700 uppercase dark:text-slate-300">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}
