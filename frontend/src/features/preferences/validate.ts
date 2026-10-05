import type { Preferences } from "@/api/client";

export function validatePreferences(value: Preferences): string | null {
  if (!value.titles.length) return "Add at least one job title.";
  if (!value.locations.length) return "Add at least one location.";
  if (!value.work_modes.length) return "Pick at least one work mode.";
  return null;
}
