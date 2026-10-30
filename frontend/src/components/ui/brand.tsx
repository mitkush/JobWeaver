import { cn } from "@/lib/cn";

/** Shared woven paths for the wordmark and loading indicator. */
export function BrandMark({ className }: { className?: string }) {
  return <svg viewBox="0 0 32 32" fill="none" className={cn("shrink-0", className)} aria-hidden="true" focusable="false"><path d="M4 7h7l10 18h7M4 25h7L21 7h7M4 16h8m8 0h8" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /><path d="m14 12 4 8" stroke="var(--jw-300, #ff7ab8)" strokeWidth="3" /></svg>;
}

/** The label remains steady while the decorative border moves once. */
export function BorderGlow() {
  return <svg className="border-glow" aria-hidden="true" focusable="false" width="100%" height="100%"><rect x="1" y="1" width="calc(100% - 2px)" height="calc(100% - 2px)" pathLength="100" /></svg>;
}
