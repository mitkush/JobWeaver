import { Copy } from "lucide-react";

import type { PossibleDuplicate } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

import { PostingRow } from "./PostingRow";

/** A Medium Match Pair: the User decides with Confirm or Not the same Job (FR-C3). */
export function PossibleDuplicateCard({
  duplicate,
  onConfirm,
  onReject,
  busy,
}: {
  duplicate: PossibleDuplicate;
  onConfirm: () => void;
  onReject: () => void;
  busy: "confirm" | "reject" | null;
}) {
  return (
    <Card className="border-amber-300 p-5 dark:border-amber-800">
      <div className="flex items-start gap-3">
        <Copy className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold">
            Possible duplicate: {duplicate.other_title}
            {duplicate.other_company && <span className="font-normal"> at {duplicate.other_company}</span>}
          </h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Is this the same opening as the job above? Your answer applies for everyone using JobWeaver.
          </p>
          <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
            {duplicate.other_postings.map((posting) => (
              <PostingRow key={posting.id} posting={{ ...posting, primary: false }} />
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={onConfirm} loading={busy === "confirm"} disabled={busy !== null}>
              Confirm
            </Button>
            <Button size="sm" variant="secondary" onClick={onReject} loading={busy === "reject"} disabled={busy !== null}>
              Not the same Job
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
