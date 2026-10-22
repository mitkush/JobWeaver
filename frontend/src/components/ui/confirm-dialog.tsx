import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./button";

/** Every destructive or outward action asks first and names its effect (UX rule 5). */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  tone = "danger",
  loading,
  confirmDisabled,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  tone?: "danger" | "primary";
  loading?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog || dialog.open) return;
    // A real modal: focus is trapped, Escape cancels and the page behind is inert.
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, [open]);

  if (!open) return null;
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      aria-labelledby="confirm-title"
      className="fixed inset-0 m-auto w-[min(28rem,calc(100%-2rem))] rounded-md border border-slate-200 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-slate-950/60 backdrop:backdrop-blur-sm dark:border-brand-500/30 dark:bg-slate-900 dark:text-slate-100 dark:shadow-[0_0_48px_-12px_rgb(255_45_146/0.45)]"
    >
      <div className="p-6">
        <h2 id="confirm-title" className="font-display text-base font-bold tracking-wide uppercase">
          {title}
        </h2>
        <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">{children}</div>
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-800">
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button variant={tone} onClick={onConfirm} loading={loading} disabled={confirmDisabled}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
