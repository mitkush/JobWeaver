import type { Content, Version } from "./api";

/** Evidence inventory, not a match score or a claim that the resume is complete. */
export function ResumeReviewGuide({ content, facts }: { content: Content; facts: Version["facts"] }) {
  const evidence = content.resume.filter(line => !line.heading && ["Experience", "Projects"].includes(line.section ?? "Experience"));
  const known = new Set(facts.map(fact => fact.ref));
  const cited = new Set(evidence.flatMap(line => line.fact_refs).filter(ref => known.has(ref)));
  return <details className="rounded border border-slate-200 p-4 dark:border-slate-700">
    <summary className="cursor-pointer font-medium">Resume review checklist · {evidence.length} work {evidence.length === 1 ? "example" : "examples"}</summary>
    <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
      <p>These work examples cite {cited.size} {cited.size === 1 ? "Fact" : "Facts"} from this Draft’s saved Fact Bank. Counts describe the content, not its quality.</p>
      <ul className="list-disc space-y-2 pl-5">
        <li>Lead with experience that demonstrates this job’s required skills: what you built, how you used the skill, and a supported result.</li>
        <li>Keep only relevant projects. Expand strong experience using Facts you can support, rather than adding projects to fill space.</li>
        <li>Review the PDF for readable type, page breaks and clipped content. Some white space is normal; filling a page is not a quality target.</li>
      </ul>
      <p>Use Edit on a section to improve it. Review any proposed AI replacement before accepting it; add missing evidence in your Fact Bank first.</p>
    </div>
  </details>;
}
