import type { JobLocation } from "@/api/client";
import { countryName } from "@/lib/countries";

export const WORK_MODES = [
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
] as const;

export function workModeLabel(mode: string | null | undefined): string | null {
  return WORK_MODES.find((m) => m.value === mode)?.label ?? null;
}

/** "Bengaluru, India", "Remote (India)", "Remote". */
export function formatLocation(location: JobLocation): string {
  const country = location.country ? countryName(location.country) : null;
  if (location.remote && !location.city) return country ? `Remote (${country})` : "Remote";
  return [location.city, country].filter(Boolean).join(", ") || "Location not given";
}
