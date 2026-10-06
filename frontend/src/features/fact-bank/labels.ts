import type { FactKind } from "@/api/client";

export const KIND_LABELS: Record<FactKind, string> = {
  skill: "Skills",
  experience: "Experience",
  project: "Projects",
  achievement: "Achievements",
  education: "Education",
  link: "Links",
  other: "Other",
};

export const KIND_ORDER: FactKind[] = [
  "skill",
  "experience",
  "project",
  "achievement",
  "education",
  "link",
  "other",
];
