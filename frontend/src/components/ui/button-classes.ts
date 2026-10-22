import { cn } from "@/lib/cn";

// Mono, uppercase, tracked labels with a cut corner on solid buttons (onebrain.run style).
// Focus outlines sit inside the button so the corner cut cannot clip them.
export const variants = {
  primary:
    "clip-corner bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/60 focus-visible:outline-offset-[-4px] focus-visible:outline-white dark:bg-brand-500 dark:text-slate-950 dark:hover:bg-brand-400 dark:shadow-[0_0_24px_-6px_rgb(255_45_146/0.6)] dark:focus-visible:outline-slate-950",
  secondary:
    "border border-slate-300 bg-white/80 text-slate-800 hover:border-brand-500 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-200 dark:hover:border-accent-400 dark:hover:text-accent-300",
  ghost:
    "text-slate-700 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800/70 dark:hover:text-white",
  danger:
    "clip-corner bg-red-600 text-white hover:bg-red-700 disabled:bg-red-600/60 focus-visible:outline-offset-[-4px] focus-visible:outline-white",
};

// Minimum heights, not fixed ones: in a narrow container a long label wraps inside the
// button and the button grows, instead of overflowing or clipping its neighbours.
export const sizes = {
  sm: "min-h-8 px-3 py-1 text-[11px]",
  md: "min-h-10 px-4 py-2 text-xs",
  lg: "min-h-11 px-6 py-2.5 text-sm",
};

export function buttonClasses(variant: keyof typeof variants = "primary", size: keyof typeof sizes = "md") {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-sm text-center leading-tight font-mono font-bold tracking-[0.12em] uppercase transition-[color,background-color,border-color,box-shadow] disabled:cursor-not-allowed disabled:opacity-60",
    variants[variant],
    sizes[size],
  );
}
