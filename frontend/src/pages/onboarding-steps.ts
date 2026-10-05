import type { Me } from "@/api/client";

export const STEPS = [
  { key: "notice", label: "AI notice" },
  { key: "country", label: "Country" },
  { key: "documents", label: "Documents" },
  { key: "review", label: "Fact Bank" },
  { key: "preferences", label: "Preferences" },
  { key: "gmail", label: "Gmail" },
] as const;
export type StepKey = (typeof STEPS)[number]["key"];

/** Maps the API's next unfinished step to the furthest screen the user may open. */
export function furthestStep(me: Me): StepKey {
  const map: Record<string, StepKey> = {
    ai_notice: "notice",
    country: "country",
    region_blocked: "country",
    documents: "documents",
    review: "review",
    preferences: "preferences",
    done: "gmail",
  };
  return map[me.onboarding.next_step] ?? "notice";
}

export const index = (key: StepKey) => STEPS.findIndex((s) => s.key === key);
