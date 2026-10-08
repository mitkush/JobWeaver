import type { SourceStatus } from "@/api/client";
import { cn } from "@/lib/cn";
import { formatQueryKey } from "@/lib/query-key";
import { shortDate } from "@/lib/time";

type Budget = NonNullable<SourceStatus["budget"]>;

/** Provider credits and separately labelled JobWeaver estimates (FR-B5). */
export function BudgetMeter({ budget }: { budget: Budget }) {
  const account = budget.account;
  const live = account?.status === "live";
  const spent = live ? account.spent! : budget.spent;
  const allowance = live ? account.allowance! : budget.allowance;
  const used = allowance > 0 ? Math.min(spent / allowance, 1) : 1;
  const projectedOver = !live && budget.projected > budget.allowance;
  const exhausted = live ? account.remaining === 0 : used >= 1;
  const tone = exhausted ? "bg-red-600" : projectedOver ? "bg-amber-500" : "bg-brand-600";

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium">
        {live ? "Apify account credits" : "JobWeaver tracked usage (estimate)"}
      </p>
      {account && !live && (
        <p className="text-xs text-amber-700 dark:text-amber-300">{account.message}</p>
      )}
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">
          {spent.toLocaleString()} / {allowance.toLocaleString()} {live ? account.unit : budget.unit}
        </span>
        <span className="text-xs text-slate-500">
          {live ? "renews" : "estimated renewal"} {shortDate(live ? account.renews_on! : budget.renews_on)}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
        role="progressbar"
        aria-label={live ? "Apify account credits used" : "JobWeaver tracked usage"}
        aria-valuemin={0}
        aria-valuemax={allowance}
        aria-valuenow={Math.min(spent, allowance)}
      >
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${used * 100}%` }} />
      </div>
      {live && (
        <p className="text-xs text-slate-500">
          {account.remaining!.toLocaleString()} US cents available for searches.
          {" "}Checked {new Date(account.checked_at!).toLocaleString()}.
          {" "}{account.message}
        </p>
      )}
      {!account && (
        <p className={cn("text-xs", projectedOver ? "text-amber-700 dark:text-amber-300" : "text-slate-500")}>
          {used >= 1
            ? "Tracked allowance used up. This source pauses until it renews."
            : budget.runs_out_on
              ? `On this pace it runs out around ${shortDate(budget.runs_out_on)}, before it renews.`
              : `On pace for about ${budget.projected.toLocaleString()} by renewal.`}
        </p>
      )}
      {live && (
        <p className="text-xs text-slate-500">
          JobWeaver tracked usage: {budget.spent.toLocaleString()} {budget.unit}.
          {" "}Search costs below exclude activity outside JobWeaver.
        </p>
      )}
      {budget.top_queries.length > 0 && (
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
