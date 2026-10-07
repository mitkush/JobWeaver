import { Star } from "lucide-react";

import { Input } from "@/components/ui/field";
import { cn } from "@/lib/cn";

export type KeywordValue = {
  keywords: string[];
  core_keywords: string[];
  keyword_min_matches: number;
  search_keywords: boolean;
};

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/** Core keywords bring differently titled jobs into a separate Feed section (FR-D1). */
export function KeywordSettings({ value, onChange }: { value: KeywordValue; onChange: (next: KeywordValue) => void }) {
  if (!value.keywords.length) return null;
  const hasCore = value.core_keywords.length > 0;

  function toggleCore(keyword: string) {
    const isCore = value.core_keywords.some((c) => same(c, keyword));
    onChange({
      ...value,
      core_keywords: isCore ? value.core_keywords.filter((c) => !same(c, keyword)) : [...value.core_keywords, keyword],
    });
  }

  return (
    <fieldset className="-mt-3 space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <legend className="px-1 text-sm font-medium text-slate-800 dark:text-slate-200">Must-have skills</legend>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Mark the skills you want to be hired for as Core. Every job in your Feed must then name at least one Core
        keyword in its title or description, including jobs that match your titles. Jobs with other titles also
        appear, in a separate section, when they name a Core keyword and {value.keyword_min_matches} of your keywords
        in total. With no Core keyword, your titles alone decide.
      </p>
      <ul className="flex flex-wrap gap-2" aria-label="Core keywords">
        {value.keywords.map((keyword) => {
          const core = value.core_keywords.some((c) => same(c, keyword));
          return (
            <li key={keyword}>
              <button
                type="button"
                aria-pressed={core}
                aria-label={`Core: ${keyword}`}
                onClick={() => toggleCore(keyword)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm",
                  core
                    ? "border-brand-600 bg-brand-600 text-white"
                    : "border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800",
                )}
              >
                <Star className={cn("size-3.5", core && "fill-current")} aria-hidden />
                {keyword}
              </button>
            </li>
          );
        })}
      </ul>
      <div className={cn("space-y-3", !hasCore && "opacity-50")}>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          Keywords a job must mention in total
          <Input
            type="number"
            min={1}
            max={10}
            value={value.keyword_min_matches}
            disabled={!hasCore}
            onChange={(e) =>
              onChange({ ...value, keyword_min_matches: Math.min(10, Math.max(1, Number(e.target.value) || 1)) })
            }
            className="w-20"
          />
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.search_keywords}
            disabled={!hasCore}
            onChange={(e) => onChange({ ...value, search_keywords: e.target.checked })}
          />
          <span>
            Also search job sites by my Core keywords
            <span className="block text-xs text-slate-500 dark:text-slate-400">
              Finds more jobs, but each Core keyword uses daily searches like a title does, within the job sites'
              budgets. Without it, Core keywords still match jobs already collected for any title.
            </span>
          </span>
        </label>
      </div>
    </fieldset>
  );
}
