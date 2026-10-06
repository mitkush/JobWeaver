import type { JobLocation } from "@/api/client";
import { countryName } from "@/lib/countries";

export const WORK_MODES = [
  { value: "onsite", label: "Onsite (office)" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote (WFH)" },
] as const;

export function workModeLabel(mode: string | null | undefined): string | null {
  return WORK_MODES.find((m) => m.value === mode)?.label ?? null;
}

/** Only the listed place; Remote/WFH is displayed separately as the work mode. */
export function formatLocation(location: JobLocation): string {
  const country = location.country ? countryName(location.country) : null;
  return [location.city, country].filter(Boolean).join(", ") || "Location not given";
}
