import { useAiUsage } from "@/api/hooks";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/cn";

/** AI calls against each provider's free daily quota, and the last week by task (FR-G4). */
export function AiUsage() {
  const usage = useAiUsage();
  if (!usage.data) return null;
  return (
    <Card>
      <CardHeader
        title="AI usage"
        description="Today's calls against each free daily quota (resets at 00:00 UTC). The gateway moves to the next provider before a quota is reached."
      />
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">AI calls today by provider and model</caption>
          <thead className="text-xs text-slate-500">
            <tr>
              <th scope="col" className="px-6 py-2 font-medium">Provider and model</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Calls today</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Errors</th>
              <th scope="col" className="px-6 py-2 text-right font-medium">Free quota</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {usage.data.models.map((m) => {
              const near = m.daily_quota !== null && m.calls_today >= m.daily_quota * 0.8;
              return (
                <tr key={`${m.provider}/${m.model}`}>
                  <th scope="row" className="px-6 py-2 font-normal">
                    {m.provider} <span className="text-slate-500">{m.model}</span>
                  </th>
                  <td className={cn("px-3 py-2 text-right", near && "font-semibold text-amber-700 dark:text-amber-300")}>
                    {m.calls_today}
                  </td>
                  <td className="px-3 py-2 text-right">{m.errors_today || "-"}</td>
                  <td className="px-6 py-2 text-right">{m.daily_quota ?? "not limited"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {usage.data.tasks_last_7_days.length > 0 && (
        <div className="overflow-x-auto border-t border-slate-200 dark:border-slate-800">
          <table className="w-full text-left text-sm">
            <caption className="px-6 pt-4 text-left text-xs font-medium text-slate-500">Last 7 days by task</caption>
            <thead className="text-xs text-slate-500">
              <tr>
                <th scope="col" className="px-6 py-2 font-medium">Task</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Calls</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Errors</th>
                <th scope="col" className="px-6 py-2 text-right font-medium">Tokens in / out</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {usage.data.tasks_last_7_days.map((t) => (
                <tr key={t.task}>
                  <th scope="row" className="px-6 py-2 font-normal">{t.task}</th>
                  <td className="px-3 py-2 text-right">{t.calls}</td>
                  <td className="px-3 py-2 text-right">{t.errors || "-"}</td>
                  <td className="px-6 py-2 text-right">
                    {t.input_tokens.toLocaleString()} / {t.output_tokens.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
