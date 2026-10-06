import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import type { PostingInfo } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { fromNow } from "@/lib/time";

import { formatLocation } from "./format";

/** One Posting in a Correspondence stack: Source, date, place and the original link. */
export function PostingRow({ posting, action }: { posting: PostingInfo; action?: ReactNode }) {
  const date = posting.posted_at ?? posting.first_seen_at;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{posting.source.label}</span>
          {posting.primary && <Badge tone="brand">Primary</Badge>}
          {posting.closed && <Badge tone="danger">No longer listed</Badge>}
        </div>
        <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
          {posting.title}
          {posting.locations.length > 0 && <> · {posting.locations.map(formatLocation).join(" / ")}</>}
          {" · "}
          {posting.posted_at ? "posted" : "found"} {fromNow(date)}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {action}
        {posting.apply_url && (
          <a
            href={posting.apply_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline dark:text-brand-100"
          >
            Open
            <ExternalLink className="size-3.5" aria-hidden />
            <span className="sr-only">(opens {posting.source.label} in a new tab)</span>
          </a>
        )}
      </div>
    </li>
  );
}
