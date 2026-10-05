import { CheckCircle2, XCircle } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";

import { ToastContext, type Toast } from "./toast-context";


export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const show = useCallback((tone: Toast["tone"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all, { id, tone, message }]);
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), 4000);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
          >
            {toast.tone === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-600" aria-hidden />
            ) : (
              <XCircle className="size-4 text-red-600" aria-hidden />
            )}
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
