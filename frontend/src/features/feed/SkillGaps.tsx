import { CheckCircle2, CircleDashed, TriangleAlert } from "lucide-react";

/** How the Job's required skills compare with the Fact Bank: matched and not found,
 * never a match score (ADR-0010). null means the advert is not analysed yet. A skill
 * not found is labelled as such: an absent Fact does not mean the User lacks it. */
export function SkillGaps({ gaps, matches, compact = false }: { gaps: string[] | null | undefined; matches?: string[] | null; compact?: boolean }) {
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
        <div className="flex items-start gap-1.5 text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <span className="font-medium">Matched:</span> <SkillNames skills={matches} compact={compact} label="matched skills" />
          </div>
        </div>
      )}
      {gaps.length > 0 ? (
        <div className="flex items-start gap-1.5 text-amber-800 dark:text-amber-300">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <span className="font-medium">Not in your Fact Bank:</span> <SkillNames skills={gaps} compact={compact} label="skills not in your Fact Bank" />
          </div>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="size-4" aria-hidden />
          Every required skill is in your Fact Bank
        </p>
      )}
    </div>
  );
}

function SkillNames({ skills, compact, label }: { skills: string[]; compact: boolean; label: string }) {
  if (!compact || skills.length <= 4) return <>{skills.join(", ")}</>;
  return <>
    {skills.slice(0, 4).join(", ")}
    <details className="mt-1">
      <summary className="cursor-pointer underline" aria-label={`Show ${skills.length - 4} more ${label}`}>+{skills.length - 4} more</summary>
      <span>{skills.slice(4).join(", ")}</span>
    </details>
  </>;
}
