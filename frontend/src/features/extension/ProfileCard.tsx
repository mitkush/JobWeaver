import { Link } from "react-router-dom";

import { useProfile, useSavedAnswers } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { buttonClasses } from "@/components/ui/button-classes";
import { Spinner } from "@/components/ui/spinner";
import { fromNow } from "@/lib/time";

/** Whether the extension has reviewed data to fill forms with (ADR-0017). */
export function ProfileCard() {
  const profile = useProfile();
  const answers = useSavedAnswers();
  if (profile.isPending) return <Spinner />;
  if (profile.isError) return <p className="text-sm text-red-700 dark:text-red-400">{profile.error.message}</p>;
  const { reviewed_at, stale } = profile.data;
  const count = answers.data?.length ?? 0;

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">Application profile</p>
          {!reviewed_at ? (
            <Badge tone="neutral">Not reviewed</Badge>
          ) : stale.length ? (
            <Badge tone="warning">Needs review</Badge>
          ) : (
            <Badge tone="success">Reviewed</Badge>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          {!reviewed_at
            ? "Review it once so the extension can fill your contact details, roles and education."
            : stale.length
              ? `${stale.length} ${stale.length === 1 ? "entry cites a Fact" : "entries cite Facts"} you changed. The extension leaves them out until you check them.`
              : `Reviewed ${fromNow(reviewed_at)}.`}{" "}
          {count === 1 ? "1 saved answer." : `${count} saved answers.`}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link to="/settings/answers" className={buttonClasses("ghost")}>
          Saved answers
        </Link>
        <Link to="/settings/profile" className={buttonClasses(reviewed_at && !stale.length ? "secondary" : "primary")}>
          {reviewed_at ? "Edit profile" : "Review profile"}
        </Link>
      </div>
    </div>
  );
}
