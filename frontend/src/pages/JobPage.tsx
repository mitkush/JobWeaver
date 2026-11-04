import { ArrowLeft, Bookmark, BookmarkCheck, Building2, ExternalLink, Mail, MapPin, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useLocation } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useConfirmDuplicate, useJob, useMarkViewed, useRejectDuplicate, useSetHidden, useSetSaved, useSplitPosting } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { JobDescription } from "@/features/feed/JobDescription";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { formatLocation, workModeLabel } from "@/features/feed/format";
import { PossibleDuplicateCard } from "@/features/feed/PossibleDuplicateCard";
import { PostingRow } from "@/features/feed/PostingRow";
import { MatchReason } from "@/features/feed/MatchReason";
import { SkillGaps } from "@/features/feed/SkillGaps";
import { fromNow } from "@/lib/time";
import { CreateDraftButton } from "@/features/drafts/CreateDraftButton";
import { statusLabel } from "@/features/applications/status";

function BackToFeed() {
  const location = useLocation();
  const from = location.state?.from;
  const destination = typeof from === "string" && /^\/feed(?:[?#]|$)/.test(from) ? from : "/feed";
  return (
    <Link to={destination} className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
      <ArrowLeft className="size-4" aria-hidden />
      Back to feed
    </Link>
  );
}

export function JobPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDuplicate();
  const reject = useRejectDuplicate();
  const split = useSplitPosting();
  const setHidden = useSetHidden();
  const setSaved = useSetSaved();
  const markViewed = useMarkViewed();
  // Viewed once the page has actually loaded, once per Job.
  const marked = useRef<string | null>(null);
  const loaded = job.data?.job_id;
  const alreadyViewed = job.data?.viewed;
  useEffect(() => {
    if (!loaded || alreadyViewed || marked.current === loaded) return;
    marked.current = loaded;
    markViewed.mutate(loaded);
  }, [loaded, alreadyViewed, markViewed]);
  const [busyPair, setBusyPair] = useState<{ id: string; action: "confirm" | "reject" } | null>(null);
  const [splitCandidate, setSplitCandidate] = useState<string | null>(null);
  const [splitting, setSplitting] = useState<string | null>(null);

  if (job.isPending) return <PageSpinner label="Loading job" />;
  if (job.isError) {
    const missing = job.error instanceof ApiError && job.error.status === 404;
    return (
      <>
        <BackToFeed />
        {missing ? (
          <EmptyState
            icon={SearchX}
            title="This job is not in your feed"
            action={
              <Link to="/feed" className={buttonClasses("secondary")}>
                Go to your feed
              </Link>
            }
          >
            It may have been merged with another job or no longer matches your preferences.
          </EmptyState>
        ) : (
          <Alert tone="error" title="The job could not load">
            {job.error.message}
          </Alert>
        )}
      </>
    );
  }

  const data = job.data;
  const mode = workModeLabel(data.work_mode);
  const primary = data.postings.find((p) => p.primary) ?? data.postings[0];
  // The Job's link is merged from every Posting, so it exists even if the primary has none.
  const advertUrl = primary?.apply_url ?? data.apply_url;
  const places = [...new Set(data.locations.map(formatLocation))];

  async function decide(pairId: string, action: "confirm" | "reject") {
    setBusyPair({ id: pairId, action });
    try {
      if (action === "confirm") {
        const merged = await confirm.mutateAsync(pairId);
        toast("success", "Merged into one job");
        if (merged.job_id === jobId) await job.refetch();
        else navigate(`/jobs/${merged.job_id}`, { replace: true });
      } else {
        await reject.mutateAsync(pairId);
        toast("success", "Kept as separate jobs");
      }
    } catch (error) {
      toast("error", (error as Error).message);
    } finally {
      setBusyPair(null);
    }
  }

  async function splitOut(postingId: string) {
    setSplitting(postingId);
    try {
      await split.mutateAsync({ jobId, postingId });
      toast("success", "Moved to a separate job");
    } catch (error) {
      toast("error", (error as Error).message);
    } finally {
      setSplitting(null);
    }
  }

  async function toggleSaved() {
    try {
      await setSaved.mutateAsync({ jobId, saved: !data.saved });
      toast("success", data.saved ? "Removed from Saved" : "Saved for later");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  async function toggleHidden() {
    try {
      await setHidden.mutateAsync({ jobId, hidden: !data.hidden });
      toast("success", data.hidden ? "Job is back in your feed" : "Job hidden from your feed");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  const applicationCard = (
    <Card>
      <CardHeader title="Your application" />
      <CardBody className="space-y-3">
        <p className="text-sm">{data.application_status ? statusLabel(data.application_status) : data.draft_id ? "Draft started" : "Not started"}</p>
        <p className="text-sm text-slate-600 dark:text-slate-400">{data.draft_id ? "Review your documents, then continue on the employer’s site." : "Read the requirements, then prepare documents from your Fact Bank."}</p>
        <div className="flex flex-wrap gap-2">
          <CreateDraftButton jobId={data.job_id} draftId={data.draft_id} disabled={data.expired && !data.draft_id} />
          <Button variant="secondary" onClick={toggleSaved} className={setSaved.isPending ? "bookmark-feedback" : undefined} loading={setSaved.isPending} aria-pressed={data.saved ?? false}>
            {data.saved ? <BookmarkCheck className="size-4" aria-hidden /> : <Bookmark className="size-4" aria-hidden />}
            {data.saved ? "Saved" : "Save"}
          </Button>
          <Button variant="ghost" onClick={toggleHidden} loading={setHidden.isPending}>
            {data.hidden ? "Show in feed" : "Hide"}
          </Button>
          {advertUrl && (
            <a href={advertUrl} target="_blank" rel="noreferrer noopener" className={buttonClasses("secondary")}>
              Open job advert
              <ExternalLink className="size-4" aria-hidden />
            </a>
          )}
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">Creating a Draft does not apply. You review and submit yourself.</p>
      </CardBody>
    </Card>
  );

  return (
    <>
      <BackToFeed />
      <ConfirmDialog open={splitCandidate !== null} title="Separate this listing?" confirmLabel="Separate listing" loading={splitting !== null} onCancel={() => setSplitCandidate(null)} onConfirm={() => { if (splitCandidate) void splitOut(splitCandidate).then(() => setSplitCandidate(null)); }}>This changes the shared Job grouping for everyone. Existing application history is kept. Only separate listings that describe different openings.</ConfirmDialog>
      {data.company_applied && (
        <Alert tone="warning" className="mb-4">
          Already applied to this Company (<Link to={`/companies/${data.company_id}`} className="underline">see your Applications there</Link>). You can still create a Draft for this Job.
        </Alert>
      )}
      {data.expired && (
        <Alert tone="warning" className="mb-4">
          This Job is closed or expired. Check the original advert before continuing.
        </Alert>
      )}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <p className="mt-1 flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
            <Building2 className="size-4" aria-hidden />
            <Link to={`/companies/${data.company_id}`} className="hover:underline" title="Your Applications to this Company">
              {data.company}
            </Link>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            {places.length > 0 && <MapPin className="size-3.5" aria-hidden />}
            {places.map((place) => (
              <Badge key={place}>{place}</Badge>
            ))}
            {mode && <Badge>{mode}</Badge>}
            {data.experience_requirement && <Badge>Experience: {data.experience_requirement}</Badge>}
            {data.application_status && <Badge>{statusLabel(data.application_status)}</Badge>}
            {data.posted_at && <span>Posted {fromNow(data.posted_at)}</span>}
          </div>
          {data.contact_email && (
            <p className="mt-2 flex items-center gap-1.5 text-sm">
              <Mail className="size-4 text-slate-500 dark:text-slate-400" aria-hidden />
              {data.contact_email}
            </p>
          )}
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:grid-rows-[auto_1fr]">
        <section aria-label="Your application" className="min-w-0 lg:col-start-2 lg:row-start-1">{applicationCard}</section>
        <div className="min-w-0 space-y-6 lg:col-start-1 lg:row-start-1 lg:row-span-2">
          <Card>
            <CardHeader title="Job description" description={data.description_origin?.kind === "page" ? "From your reviewed careers-page description" : primary ? `From ${primary.source.label}` : undefined} />
            <CardBody>
              {typeof data.description_origin?.url === "string" && <a className="mb-4 inline-block text-sm underline" href={data.description_origin.url} target="_blank" rel="noreferrer noopener">Open description source</a>}
              <JobDescription text={data.description} />
            </CardBody>
          </Card>
      {data.possible_duplicates.length > 0 && (
        <section id="possible-duplicates" aria-label="Possible duplicates" className="mb-6 space-y-3">
          {data.possible_duplicates.map((duplicate) => (
            <PossibleDuplicateCard
              key={duplicate.pair_id}
              duplicate={duplicate}
              busy={busyPair?.id === duplicate.pair_id ? busyPair.action : null}
              onConfirm={() => decide(duplicate.pair_id, "confirm")}
              onReject={() => decide(duplicate.pair_id, "reject")}
            />
          ))}
        </section>
      )}

          {(data.archived_drafts ?? []).length > 0 && (
            <details className="rounded border border-slate-200 p-4 dark:border-slate-700">
              <summary className="cursor-pointer font-medium">Archived Drafts ({data.archived_drafts!.length})</summary>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                Earlier packages for this Job, kept with their versions and any application they were used for.
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {data.archived_drafts!.map((draft) => (
                  <li key={draft.id}>
                    <Link to={`/drafts/${draft.id}`} className="underline">
                      Draft from {new Date(draft.created_at).toLocaleDateString()}, version {draft.current_version}
                    </Link>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details className="rounded border border-slate-200 p-4 dark:border-slate-700">
            <summary className="cursor-pointer font-medium">Sources and listing details (Correspondence)</summary>
          <Card>
            <CardHeader
              title="Correspondence"
              description={`Every posting of this job, across ${data.postings.length === 1 ? "1 source" : `${new Set(data.postings.map((p) => p.source.name)).size} sources`}.`}
            />
            <CardBody className="py-1">
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {data.postings.map((posting) => (
                  <PostingRow
                    key={posting.id}
                    posting={posting}
                    action={
                      data.postings.length > 1 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSplitCandidate(posting.id)}
                          loading={splitting === posting.id}
                          disabled={splitting !== null}
                          title="Move this posting to a separate job, for everyone"
                        >
                          Not the same Job
                        </Button>
                      )
                    }
                  />
                ))}
              </ul>
            </CardBody>
          </Card>
          </details>

        </div>
        <aside aria-label="Skills comparison" className="min-w-0 lg:col-start-2 lg:row-start-2">
          <Card>
            <CardHeader title="Skills" description="Required by the job, compared with your Fact Bank." />
            <CardBody className="space-y-3">
              <MatchReason match={data.match} matched_keywords={data.matched_keywords} />
              <SkillGaps gaps={data.skill_gaps} matches={data.skill_matches} />
              {Object.keys(data.keyword_evidence ?? {}).length > 0 && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">Why these keywords matched</summary>
                  <ul className="mt-3 space-y-3 text-sm">
                    {Object.entries(data.keyword_evidence ?? {}).map(([keyword, evidence]) => (
                      <li key={keyword}>
                        <p className="font-medium">{keyword}</p>
                        <blockquote className="mt-1 border-l-2 border-brand-400 pl-3 text-slate-600 dark:text-slate-300">
                          {evidence}
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-slate-500">
                    Original Source description. Skill context is checked once per Job description, not on each Feed view.
                  </p>
                </details>
              )}

            </CardBody>
          </Card>
        </aside>
      </div>
    </>
  );
}
