import { Bookmark, BookmarkCheck, Copy, Eye, EyeOff, MapPin } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import type { FeedCard } from "@/api/client";
import { useSetHidden, useSetSaved } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast-context";
import { fromNow } from "@/lib/time";

import { rememberScroll } from "./feed-memory";
import { formatLocation, workModeLabel } from "./format";
import { MatchReason } from "./MatchReason";
import { SkillGaps } from "./SkillGaps";
import { SourceBadges } from "./SourceBadges";
import { CreateDraftButton } from "@/features/drafts/CreateDraftButton";
import { statusLabel } from "@/features/applications/status";

export function JobCard({ job }: { job: FeedCard }) {
  const location = useLocation();
  const setHidden = useSetHidden();
  const setSaved = useSetSaved();
  const toast = useToast();
  const from = location.pathname + location.search;
  const open = () => rememberScroll(location.search);
  const mode = workModeLabel(job.work_mode);
  const places = [...new Set(job.locations.map(formatLocation))];

  async function toggleHidden() {
    try {
      await setHidden.mutateAsync({ jobId: job.job_id, hidden: !job.hidden });
      toast("success", job.hidden ? "Job is back in your feed" : "Job hidden from your feed");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  async function toggleSaved() {
    try {
      await setSaved.mutateAsync({ jobId: job.job_id, saved: !job.saved });
      toast("success", job.saved ? "Removed from Saved" : "Saved for later");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <Card className="p-5 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">
            {/* Opening the Job is the Feed's one main action (UX rule 1). */}
            <Link to={`/jobs/${job.job_id}`} state={{ from }} onClick={open} className="hover:text-brand-700 focus-visible:underline dark:hover:text-brand-100">
              {job.title}
            </Link>
          </h2>
          <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">{job.company}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleSaved}
            loading={setSaved.isPending}
            aria-pressed={job.saved ?? false}
            aria-label={`Save ${job.title}`}
            title={job.saved ? "Saved: click to remove" : "Save for later"}
          >
            {job.saved ? (
              <BookmarkCheck className="size-4 text-brand-600 dark:text-brand-300" aria-hidden />
            ) : (
              <Bookmark className="size-4" aria-hidden />
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleHidden}
            loading={setHidden.isPending}
            aria-label={job.hidden ? `Show ${job.title} again` : `Hide ${job.title}`}
          >
            {job.hidden ? <Eye className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-slate-600 dark:text-slate-400">
        {places.length > 0 && (
          <span className="flex flex-wrap items-center gap-1">
            <MapPin className="size-3.5" aria-hidden />
            {places.map((place) => (
              <Badge key={place}>{place}</Badge>
            ))}
          </span>
        )}
        {mode && <Badge>{mode}</Badge>}
        {job.experience_requirement && <Badge>{job.experience_requirement} experience</Badge>}
        {job.posted_at && <span>Posted {fromNow(job.posted_at)}</span>}
        {job.viewed && <span className="text-xs text-slate-500 dark:text-slate-400">Viewed</span>}
        {job.expired && <Badge tone="warning">Expired</Badge>}
        {job.hidden && job.saved && <Badge>Hidden</Badge>}
        {job.possible_duplicate && (
          <Link to={`/jobs/${job.job_id}#possible-duplicates`} state={{ from }} onClick={open}>
            <Badge tone="warning" className="gap-1">
              <Copy className="size-3" aria-hidden />
              Possible duplicate
            </Badge>
          </Link>
        )}
      </div>

      <div className="mt-3 space-y-2">
        <MatchReason match={job.match} matched_keywords={job.matched_keywords} />
        <SkillGaps gaps={job.skill_gaps} matches={job.skill_matches} />
        <SourceBadges sources={job.sources} />
        {job.company_applied && <p className="text-xs text-amber-700 dark:text-amber-300">Already applied to this Company</p>}
        {job.application_status && <Badge>{statusLabel(job.application_status)}</Badge>}
        <CreateDraftButton jobId={job.job_id} draftId={job.draft_id} />
      </div>
    </Card>
  );
}
