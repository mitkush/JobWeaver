import { CheckCircle2, CircleDashed, TriangleAlert } from "lucide-react";

/** How the Job's required skills compare with the Fact Bank: matched and not found,
 * never a match score (ADR-0010). null means the advert is not analysed yet. A skill
 * not found is labelled as such: an absent Fact does not mean the User lacks it. */
export function SkillGaps({ gaps, matches, compact = false }: { gaps: string[] | null | undefined; matches?: string[] | null; compact?: boolean }) {
  if (compact && (gaps?.length ?? 0) + (matches?.length ?? 0) > 5) return <details className="text-sm"><summary className="cursor-pointer text-slate-600 dark:text-slate-300">Skills: {matches?.length ?? 0} matched · {gaps?.length ?? 0} not in Fact Bank</summary><div className="mt-2"><SkillGaps gaps={gaps} matches={matches} /></div></details>;
  if (gaps == null) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
        <CircleDashed className="size-4" aria-hidden />
        Skills not analysed yet
      </p>
    );
  }
  return (
    <div className="space-y-1 text-sm">
      {matches && matches.length > 0 && (
        <p className="flex items-start gap-1.5 text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <span className="font-medium">Matched:</span> {matches.join(", ")}
          </span>
        </p>
      )}
      {gaps.length > 0 ? (
        <p className="flex items-start gap-1.5 text-amber-800 dark:text-amber-300">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <span className="font-medium">Not in your Fact Bank:</span> {gaps.join(", ")}
          </span>
        </p>
      ) : (
        <p className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="size-4" aria-hidden />
          Every required skill is in your Fact Bank
        </p>
      )}
    </div>
  );
}
