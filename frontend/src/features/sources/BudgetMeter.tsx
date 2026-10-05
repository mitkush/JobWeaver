import type { SourceStatus } from "@/api/client";
import { cn } from "@/lib/cn";
import { formatQueryKey } from "@/lib/query-key";
import { shortDate } from "@/lib/time";

type Budget = NonNullable<SourceStatus["budget"]>;

/** Spend against the free allowance, with the month-end projection (FR-B5). */
export function BudgetMeter({ budget }: { budget: Budget }) {
  const used = Math.min(budget.spent / budget.allowance, 1);
  const projectedOver = budget.projected > budget.allowance;
  const tone = used >= 1 ? "bg-red-600" : projectedOver ? "bg-amber-500" : "bg-brand-600";

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">
          {budget.spent.toLocaleString()} / {budget.allowance.toLocaleString()} {budget.unit}
        </span>
        <span className="text-xs text-slate-500">renews {shortDate(budget.renews_on)}</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
        role="progressbar"
        aria-label={`${budget.unit} used`}
        aria-valuemin={0}
        aria-valuemax={budget.allowance}
        aria-valuenow={budget.spent}
      >
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${used * 100}%` }} />
      </div>
      <p className={cn("text-xs", projectedOver ? "text-amber-700 dark:text-amber-300" : "text-slate-500")}>
        {used >= 1
          ? "Used up. This source pauses until it renews."
          : budget.runs_out_on
            ? `On this pace it runs out around ${shortDate(budget.runs_out_on)}, before it renews.`
            : `On pace for about ${budget.projected.toLocaleString()} by renewal.`}
      </p>
      {projectedOver && budget.top_queries.length > 0 && (
        <div className="text-xs text-slate-600 dark:text-slate-400">
          <p className="font-medium">Most expensive searches this month</p>
          <ul className="mt-1 space-y-0.5">
            {budget.top_queries.map((q) => (
              <li key={q.query_key} className="flex justify-between gap-4">
                <span className="truncate">{formatQueryKey(q.query_key)}</span>
                <span>{q.spent}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
