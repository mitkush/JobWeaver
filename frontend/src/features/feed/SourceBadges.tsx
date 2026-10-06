import type { Schemas } from "@/api/client";
import { Badge } from "@/components/ui/badge";

/** "Available on" badges: every Source in the Job's stack (FR-C6). */
export function SourceBadges({ sources }: { sources: Schemas["SourceBadge"][] }) {
  if (!sources.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-slate-500 dark:text-slate-400">Available on</span>
      {sources.map((source) => (
        <Badge key={source.name} tone="brand">
          {source.label}
        </Badge>
      ))}
    </div>
  );
}
