import { Plus } from "lucide-react";

import { useTitleSuggestions } from "@/api/hooks";

/** The most titles Preferences accept (PreferencesIn.titles). */
export const MAX_TITLES = 20;

/** Related titles the User can add with one click. Nothing is searched until added. */
export function TitleSuggestions({ titles, onAdd }: { titles: string[]; onAdd: (title: string) => void }) {
  const suggestions = useTitleSuggestions(titles);
  const full = titles.length >= MAX_TITLES;
  const offered = suggestions.data?.titles.filter((t) => !titles.some((have) => have.toLowerCase() === t.toLowerCase()));
  if (!offered?.length) return null;
  const searches = suggestions.data?.searches_per_title ?? 0;
  return (
    <div className="mt-2 space-y-1.5">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Related titles, so jobs named differently are found too.
        {full
          ? ` You have the maximum of ${MAX_TITLES} titles; remove one to add another.`
          : searches > 0 &&
            ` Each title you add uses about ${searches} more search${searches === 1 ? "" : "es"} a day from the paid job sites' budgets.`}
      </p>
      <ul className="flex flex-wrap gap-2" aria-label="Suggested titles">
        {offered.map((title) => (
          <li key={title}>
            <button
              type="button"
              disabled={full}
              onClick={() => onAdd(title)}
              aria-label={`Add title ${title}`}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-3 py-1 text-sm text-slate-700 enabled:hover:border-brand-600 enabled:hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:text-brand-100"
            >
              <Plus className="size-3.5" aria-hidden />
              {title}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
