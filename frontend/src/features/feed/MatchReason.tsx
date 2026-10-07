import { Info, Star } from "lucide-react";

import type { FeedCard } from "@/api/client";
import { Badge } from "@/components/ui/badge";

type Props = Pick<FeedCard, "match" | "matched_keywords">;

/** Why a Job is in the Feed when it is not simply a title match. Never a score (ADR-0010). */
export function MatchReason({ match, matched_keywords: keywords = [] }: Props) {
  if (match === null) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
        <Info className="size-4" aria-hidden />
        No longer matches your Preferences; kept because you drafted, applied or hid it.
      </p>
    );
  }
  if (match !== "keywords" || !keywords.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400">
      <span>Matches your keywords:</span>
      <ul className="flex flex-wrap gap-1.5" aria-label="Matched keywords">
        {keywords.map((k) => (
          <li key={k.keyword}>
            <Badge tone={k.core ? "brand" : "neutral"} className="gap-1">
              {k.core && <Star className="size-3 fill-current" aria-label="Core" />}
              {k.keyword}
              <span className="font-normal opacity-75">
                {k.where === "requirements" ? "in requirements" : "in description"}
              </span>
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
