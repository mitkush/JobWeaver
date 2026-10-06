import { CheckCircle2, CircleDashed, TriangleAlert } from "lucide-react";

/** Skill Gaps, never a match score (ADR-0010). null means not analysed yet. */
export function SkillGaps({ gaps }: { gaps: string[] | null | undefined }) {
  if (gaps == null) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
        <CircleDashed className="size-4" aria-hidden />
        Required skills not analysed yet
      </p>
    );
  }
  if (gaps.length === 0) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-300">
        <CheckCircle2 className="size-4" aria-hidden />
        No gaps found
      </p>
    );
  }
  return (
    <p className="flex items-start gap-1.5 text-sm text-amber-800 dark:text-amber-300">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>
        <span className="font-medium">Missing:</span> {gaps.join(", ")}
      </span>
    </p>
  );
}
