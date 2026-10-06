import { ArrowLeft, Building2, ExternalLink, Mail, MapPin, SearchX } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useConfirmDuplicate, useJob, useRejectDuplicate, useSetHidden, useSplitPosting } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { formatLocation, workModeLabel } from "@/features/feed/format";
import { PossibleDuplicateCard } from "@/features/feed/PossibleDuplicateCard";
import { PostingRow } from "@/features/feed/PostingRow";
import { SkillGaps } from "@/features/feed/SkillGaps";
import { fromNow } from "@/lib/time";
import { CreateDraftButton } from "@/features/drafts/CreateDraftButton";

function BackToFeed() {
  return (
    <Link to="/feed" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
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
  const [busyPair, setBusyPair] = useState<{ id: string; action: "confirm" | "reject" } | null>(null);
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
  const places = [...new Set(data.locations.map(formatLocation))].filter((place) => !(mode === "Remote" && place === "Remote"));

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

  async function toggleHidden() {
    try {
      await setHidden.mutateAsync({ jobId, hidden: !data.hidden });
      toast("success", data.hidden ? "Job is back in your feed" : "Job hidden from your feed");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <>
      <BackToFeed />
      {data.company_applied && <Alert tone="warning" className="mb-4">Already applied to this Company. You can still create a Draft for this Job.</Alert>}
      {data.expired && (
        <Alert tone="warning" className="mb-4">
          This job is no longer listed by any source.
        </Alert>
      )}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <p className="mt-1 flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
            <Building2 className="size-4" aria-hidden />
            {data.company}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            {places.length > 0 && <MapPin className="size-3.5" aria-hidden />}
            {places.map((place) => (
              <Badge key={place}>{place}</Badge>
            ))}
            {mode && <Badge>{mode}</Badge>}
            {data.application_status && <Badge>{data.application_status === "applied" ? "Applied" : "Drafted"}</Badge>}
            {data.posted_at && <span>Posted {fromNow(data.posted_at)}</span>}
          </div>
          {data.contact_email && (
            <p className="mt-2 flex items-center gap-1.5 text-sm">
              <Mail className="size-4 text-slate-500" aria-hidden />
              {data.contact_email}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <CreateDraftButton jobId={data.job_id} draftId={data.draft_id} disabled={data.expired && !data.draft_id} />
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
      </div>

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

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-6">
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
                          onClick={() => splitOut(posting.id)}
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
          <Card>
            <CardHeader title="Job description" description={primary ? `From ${primary.source.label}` : undefined} />
            <CardBody>
              <div className="text-sm leading-relaxed whitespace-pre-line text-slate-700 dark:text-slate-300">
                {data.description || "No description was provided."}
              </div>
            </CardBody>
          </Card>
        </div>
        <aside>
          <Card>
            <CardHeader title="Skills" description="Required by the job, compared with your Fact Bank." />
            <CardBody className="space-y-3">
              <SkillGaps gaps={data.skill_gaps} />
              {data.required_skills && data.required_skills.length > 0 && (
                <ul className="flex flex-wrap gap-1.5" aria-label="Required skills">
                  {data.required_skills.map((skill) => {
                    const missing = data.skill_gaps?.includes(skill);
                    return (
                      <li key={skill}>
                        <Badge tone={missing ? "warning" : "success"}>
                          {skill}
                          <span className="sr-only">{missing ? " (missing)" : " (you have it)"}</span>
                        </Badge>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardBody>
          </Card>
        </aside>
      </div>
    </>
  );
}
