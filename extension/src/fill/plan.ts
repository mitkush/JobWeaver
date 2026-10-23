/** What JobWeaver would put in each field: the reviewed profile and the chosen Draft's
 * PDFs, nothing else (ADR-0017). Sensitive and free-text questions are left out here. */

import type { Field, FieldKey } from "./types";

export type Profile = {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  city?: string;
  country?: string | null;
  links?: { label: string; url: string }[];
  employment?: { employer: string; title?: string; current?: boolean }[];
  education?: { school: string; degree?: string }[];
};

export type Files = { resume: string; cover_letter: string };

export type Proposal = {
  ref: string;
  label: string;
  key: FieldKey;
  /** Shown in the preview; for files, the PDF's name. */
  value: string;
  source: "profile" | "draft";
  /** Fields that already hold something are only overwritten when the User ticks them. */
  overwrite: boolean;
};

const countryNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" });
  } catch {
    return null;
  }
})();

export function countryName(code: string | null | undefined): string {
  if (!code) return "";
  return countryNames?.of(code) ?? code;
}

function link(profile: Profile, label: string): string {
  return profile.links?.find((l) => l.label === label)?.url ?? "";
}

function currentRole(profile: Profile) {
  return profile.employment?.find((e) => e.current) ?? profile.employment?.[0];
}

export function valueFor(key: FieldKey, profile: Profile, files: Files | null): string {
  const full = [profile.first_name, profile.last_name].filter(Boolean).join(" ");
  const country = countryName(profile.country);
  switch (key) {
    case "first_name":
      return profile.first_name ?? "";
    case "last_name":
      return profile.last_name ?? "";
    case "full_name":
      return full;
    case "email":
      return profile.email ?? "";
    case "phone":
      return profile.phone ?? "";
    case "city":
      return profile.city ?? "";
    case "country":
      return country;
    case "location":
      return [profile.city, country].filter(Boolean).join(", ");
    case "linkedin":
    case "github":
    case "portfolio":
      return link(profile, key);
    case "website":
      return link(profile, "website") || link(profile, "portfolio");
    case "current_company":
      return currentRole(profile)?.employer ?? "";
    case "current_title":
      return currentRole(profile)?.title ?? "";
    case "school":
      return profile.education?.[0]?.school ?? "";
    case "degree":
      return profile.education?.[0]?.degree ?? "";
    case "resume":
    case "cover_letter":
      return files?.[key] ?? "";
  }
}

/** The option a select should take for a value: same text, else the only option that
 * contains it. Ambiguous or missing choices are left for the User. */
export function optionFor(options: string[], value: string, code?: string | null): string | null {
  const want = value.trim().toLowerCase();
  if (!want) return null;
  const exact = options.find((o) => o.trim().toLowerCase() === want || (code && o.trim().toUpperCase() === code));
  if (exact) return exact;
  const partial = options.filter((o) => o.toLowerCase().includes(want));
  return partial.length === 1 ? partial[0]! : null;
}

export function propose(fields: Field[], profile: Profile | null, files: Files | null): Proposal[] {
  const proposals: Proposal[] = [];
  for (const field of fields) {
    if (!field.key) continue;
    const isFile = field.key === "resume" || field.key === "cover_letter";
    if (isFile !== (field.kind === "file")) continue;
    let value = isFile ? valueFor(field.key, {}, files) : profile ? valueFor(field.key, profile, null) : "";
    if (field.kind === "select") {
      value = optionFor(field.options ?? [], value, field.key === "country" ? profile?.country : null) ?? "";
    }
    if (!value) continue;
    proposals.push({
      ref: field.ref,
      label: field.label,
      key: field.key,
      value,
      source: isFile ? "draft" : "profile",
      overwrite: field.hasValue,
    });
  }
  return proposals;
}
