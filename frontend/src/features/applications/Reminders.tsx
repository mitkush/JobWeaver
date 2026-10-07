import { BellRing } from "lucide-react";
import { useState } from "react";

import type { Reminder } from "@/api/client";
import { useDismissReminder, useReminders } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast-context";

import { FollowUpDialog } from "./FollowUpDialog";

/** In-app Follow-up Reminders (FR-F2): one line each, with "Draft a follow-up" as the action. */
export function Reminders() {
  const reminders = useReminders();
  const dismiss = useDismissReminder();
  const toast = useToast();
  const [open, setOpen] = useState<Reminder | null>(null);
  const items = reminders.data ?? [];
  if (items.length === 0) return null;

  return (
    <section aria-labelledby="reminders-title" className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/40">
      <h2 id="reminders-title" className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-100">
        <BellRing className="size-4" aria-hidden />
        Follow-ups due
      </h2>
      <ul className="mt-2 divide-y divide-amber-200 dark:divide-amber-900">
        {items.map((reminder) => (
          <li key={reminder.application_id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
            <span className="text-amber-950 dark:text-amber-50">
              No update from {reminder.company} for {reminder.days_waiting} days ({reminder.title})
            </span>
            <span className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                loading={dismiss.isPending && dismiss.variables === reminder.application_id}
                onClick={async () => {
                  try {
                    await dismiss.mutateAsync(reminder.application_id);
                  } catch (error) {
                    toast("error", (error as Error).message);
                  }
                }}
              >
                Not now
              </Button>
              <Button size="sm" onClick={() => setOpen(reminder)}>
                Draft a follow-up
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {open && <FollowUpDialog reminder={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
