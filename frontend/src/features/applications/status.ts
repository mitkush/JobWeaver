import type { ApplicationStatus } from "@/api/client";

/** Tracker order (FR-F1): Drafted -> Applied -> Replied -> Interview -> Offer, or Rejected. */
export const STATUSES: { id: ApplicationStatus; label: string }[] = [
  { id: "drafted", label: "Drafted" },
  { id: "applied", label: "Applied" },
  { id: "replied", label: "Replied" },
  { id: "interview", label: "Interview" },
  { id: "offer", label: "Offer" },
  { id: "rejected", label: "Rejected" },
];

export function statusLabel(status: string): string {
  return STATUSES.find((s) => s.id === status)?.label ?? status;
}
