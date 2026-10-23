import { Plus, Trash2 } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, type ApplicationProfile, type ProfileContent } from "@/api/client";
import { useProfile, useProfileSuggestion, useSaveProfile } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/field";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { cn } from "@/lib/cn";
import { COUNTRIES } from "@/lib/countries";

type Link = { label: "linkedin" | "github" | "portfolio" | "website" | "other"; url: string; fact_id: string | null };
type Job = {
  employer: string;
  title: string;
  location: string;
  start: string | null;
  end: string | null;
  current: boolean;
  fact_ids: string[];
};
type School = { school: string; degree: string; field: string; start: string | null; end: string | null; fact_ids: string[] };
/** The profile with every default filled in, as the form edits it. */
type Content = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  phone_fact_id: string | null;
  city: string;
  country: string | null;
  links: Link[];
  employment: Job[];
  education: School[];
};

function normalize(c: ProfileContent | null | undefined): Content {
  return {
    first_name: c?.first_name ?? "",
    last_name: c?.last_name ?? "",
    email: c?.email ?? "",
    phone: c?.phone ?? "",
    phone_fact_id: c?.phone_fact_id ?? null,
    city: c?.city ?? "",
    country: c?.country ?? null,
    links: (c?.links ?? []).map((l) => ({ label: l.label, url: l.url, fact_id: l.fact_id ?? null })),
    employment: (c?.employment ?? []).map((e) => ({
      employer: e.employer,
      title: e.title ?? "",
      location: e.location ?? "",
      start: e.start ?? null,
      end: e.end ?? null,
      current: e.current ?? false,
      fact_ids: e.fact_ids ?? [],
    })),
    education: (c?.education ?? []).map((e) => ({
      school: e.school,
      degree: e.degree ?? "",
      field: e.field ?? "",
      start: e.start ?? null,
      end: e.end ?? null,
      fact_ids: e.fact_ids ?? [],
    })),
  };
}

const LINK_LABELS: { value: Link["label"]; name: string }[] = [
  { value: "linkedin", name: "LinkedIn" },
  { value: "github", name: "GitHub" },
  { value: "portfolio", name: "Portfolio" },
  { value: "website", name: "Website" },
  { value: "other", name: "Other" },
];

const MONTH_HINT = "YYYY-MM or YYYY";
const MONTH = /^\d{4}(-(0[1-9]|1[0-2]))?$/;

/** The reviewed data the browser extension fills forms with (ADR-0017). */
export function ApplicationProfilePage() {
  const profile = useProfile();
  if (profile.isPending) return <PageSpinner />;
  if (profile.isError) return <Alert tone="error">{profile.error.message}</Alert>;
  return <ProfileForm key={profile.data.version} profile={profile.data} />;
}

function ProfileForm({ profile }: { profile: ApplicationProfile }) {
  const [content, setContent] = useState<Content>(() => normalize(profile.content));
  // Paths of entries whose Facts changed since the review; cleared once edited here.
  const [stale, setStale] = useState(new Set(profile.stale));
  const suggestion = useProfileSuggestion();
  const save = useSaveProfile();
  const toast = useToast();
  const set = (patch: Partial<Content>) => setContent((c) => ({ ...c, ...patch }));
  const datesValid = [...content.employment, ...content.education].every(
    (e) => (!e.start || MONTH.test(e.start)) && (!e.end || MONTH.test(e.end)),
  );
  const complete =
    content.employment.every((e) => e.employer.trim()) &&
    content.education.every((e) => e.school.trim()) &&
    content.links.every((l) => l.url.trim());

  function update<K extends "links" | "employment" | "education">(key: K, index: number, patch: Partial<Content[K][number]>) {
    setContent((c) => ({ ...c, [key]: c[key].map((item, i) => (i === index ? ({ ...item, ...patch }) as Content[K][number] : item)) }));
  }

  function remove(key: "links" | "employment" | "education", index: number) {
    setContent((c) => ({ ...c, [key]: c[key].filter((_, i) => i !== index) }));
    // Later entries shift up; their highlights would point at the wrong row.
    setStale(new Set());
  }

  async function loadSuggestion() {
    try {
      setContent(normalize(await suggestion.mutateAsync()));
      setStale(new Set());
      toast("success", "Filled from your Fact Bank. Check every value, then save.");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  async function onSave() {
    try {
      await save.mutateAsync({ content: { ...content, phone_fact_id: content.phone ? content.phone_fact_id : null }, expected_version: profile.version });
      toast("success", "Profile saved. The extension can use it now.");
    } catch (error) {
      toast("error", error instanceof ApiError && error.status === 409 ? "Your profile changed in another tab. Reload the page." : (error as Error).message);
    }
  }

  const flagged = (path: string) => stale.has(path);

  return (
    <>
      <PageHeader
        title="Application profile"
        description="What the browser extension fills into application forms. Nothing here is written by AI, and the extension only uses it after you save."
        action={
          <Link to="/settings" className={buttonClasses("ghost")}>
            Back to Settings
          </Link>
        }
      />
      <div className="space-y-6">
        {profile.content === null && (
          <Alert tone="info" title="Not reviewed yet">
            Start from your Fact Bank, check every value, then save. The extension fills nothing until you do.
          </Alert>
        )}
        {stale.size > 0 && (
          <Alert tone="warning" title="Your Fact Bank changed">
            The highlighted entries cite Facts you changed or removed. The extension leaves them out until you check them and save.
          </Alert>
        )}

        <Card>
          <CardHeader
            title="Contact"
            action={
              <Button variant="secondary" loading={suggestion.isPending} onClick={loadSuggestion}>
                Fill from Fact Bank
              </Button>
            }
          />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field label="First name" htmlFor="p-first">
              <Input id="p-first" autoComplete="off" value={content.first_name} onChange={(e) => set({ first_name: e.target.value })} />
            </Field>
            <Field label="Last name" htmlFor="p-last">
              <Input id="p-last" autoComplete="off" value={content.last_name} onChange={(e) => set({ last_name: e.target.value })} />
            </Field>
            <Field label="Email" htmlFor="p-email">
              <Input id="p-email" type="email" value={content.email} onChange={(e) => set({ email: e.target.value })} />
            </Field>
            <div className={cn(flagged("phone") && "rounded-md ring-2 ring-amber-400 ring-offset-4 ring-offset-white dark:ring-offset-slate-950")}>
              <Field label="Phone" htmlFor="p-phone">
                <Input id="p-phone" type="tel" value={content.phone} onChange={(e) => set({ phone: e.target.value })} />
              </Field>
            </div>
            <Field label="City" htmlFor="p-city">
              <Input id="p-city" value={content.city} onChange={(e) => set({ city: e.target.value })} />
            </Field>
            <Field label="Country" htmlFor="p-country">
              <Select id="p-country" value={content.country ?? ""} onChange={(e) => set({ country: e.target.value || null })}>
                <option value="">Not set</option>
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Links"
            action={
              <Button variant="ghost" disabled={content.links.length >= 10} onClick={() => set({ links: [...content.links, { label: "portfolio", url: "", fact_id: null }] })}>
                <Plus className="size-4" aria-hidden />
                Add link
              </Button>
            }
          />
          <CardBody className="space-y-3">
            {content.links.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">No links yet.</p>}
            {content.links.map((link, i) => (
              <Row key={i} flagged={flagged(`links.${i}`)} onRemove={() => remove("links", i)} name={`link ${i + 1}`}>
                <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
                  <Field label="Kind" htmlFor={`l-kind-${i}`}>
                    <Select id={`l-kind-${i}`} value={link.label} onChange={(e) => update("links", i, { label: e.target.value as Link["label"] })}>
                      {LINK_LABELS.map((l) => (
                        <option key={l.value} value={l.value}>
                          {l.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Address" htmlFor={`l-url-${i}`}>
                    <Input id={`l-url-${i}`} type="url" value={link.url} onChange={(e) => update("links", i, { url: e.target.value })} />
                  </Field>
                </div>
              </Row>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Employment"
            action={
              <Button
                variant="ghost"
                disabled={content.employment.length >= 20}
                onClick={() =>
                  set({ employment: [...content.employment, { employer: "", title: "", location: "", start: null, end: null, current: false, fact_ids: [] }] })
                }
              >
                <Plus className="size-4" aria-hidden />
                Add role
              </Button>
            }
          />
          <CardBody className="space-y-3">
            {content.employment.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">No roles yet.</p>}
            {content.employment.map((job, i) => (
              <Row key={i} flagged={flagged(`employment.${i}`)} onRemove={() => remove("employment", i)} name={job.employer || `role ${i + 1}`}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Text id={`e-employer-${i}`} label="Employer" value={job.employer} onChange={(v) => update("employment", i, { employer: v })} />
                  <Text id={`e-title-${i}`} label="Title" value={job.title} onChange={(v) => update("employment", i, { title: v })} />
                  <Text id={`e-location-${i}`} label="Location" value={job.location} onChange={(v) => update("employment", i, { location: v })} />
                  <DateInput id={`e-start-${i}`} label="Start" value={job.start} onChange={(v) => update("employment", i, { start: v })} />
                  <DateInput
                    id={`e-end-${i}`}
                    label="End"
                    value={job.current ? null : job.end}
                    disabled={job.current}
                    onChange={(v) => update("employment", i, { end: v } as Partial<Job>)}
                  />
                  <label className="flex items-center gap-2 self-end pb-2 text-sm">
                    <input
                      type="checkbox"
                      checked={job.current}
                      onChange={(e) => update("employment", i, { current: e.target.checked, end: e.target.checked ? null : job.end })}
                    />
                    I work here now
                  </label>
                </div>
              </Row>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Education"
            action={
              <Button
                variant="ghost"
                disabled={content.education.length >= 10}
                onClick={() => set({ education: [...content.education, { school: "", degree: "", field: "", start: null, end: null, fact_ids: [] }] })}
              >
                <Plus className="size-4" aria-hidden />
                Add school
              </Button>
            }
          />
          <CardBody className="space-y-3">
            {content.education.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">No education yet.</p>}
            {content.education.map((school, i) => (
              <Row key={i} flagged={flagged(`education.${i}`)} onRemove={() => remove("education", i)} name={school.school || `school ${i + 1}`}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Text id={`s-school-${i}`} label="School" value={school.school} onChange={(v) => update("education", i, { school: v } as Partial<School>)} />
                  <Text id={`s-degree-${i}`} label="Degree" value={school.degree} onChange={(v) => update("education", i, { degree: v })} />
                  <Text id={`s-field-${i}`} label="Field of study" value={school.field} onChange={(v) => update("education", i, { field: v })} />
                  <DateInput id={`s-start-${i}`} label="Start" value={school.start} onChange={(v) => update("education", i, { start: v })} />
                  <DateInput id={`s-end-${i}`} label="End" value={school.end} onChange={(v) => update("education", i, { end: v })} />
                </div>
              </Row>
            ))}
          </CardBody>
        </Card>

        <div className="flex flex-wrap items-center gap-3">
          <Button loading={save.isPending} disabled={!datesValid || !complete} onClick={onSave}>
            Save and mark reviewed
          </Button>
          {!datesValid && <p className="text-sm text-red-700 dark:text-red-400">Write dates as {MONTH_HINT}.</p>}
          {datesValid && !complete && <p className="text-sm text-red-700 dark:text-red-400">Every role needs an employer, every school a name, every link an address.</p>}
        </div>
      </div>
    </>
  );
}

function Row({ flagged, onRemove, name, children }: { flagged: boolean; onRemove: () => void; name: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border p-4",
        flagged ? "border-amber-400 bg-amber-50 dark:border-amber-500/60 dark:bg-amber-950/30" : "border-slate-200 dark:border-slate-800",
      )}
    >
      <div className="min-w-0 flex-1">
        {flagged && <p className="mb-3 text-sm font-medium text-amber-800 dark:text-amber-300">The Fact behind this changed. Check it.</p>}
        {children}
      </div>
      <Button variant="ghost" aria-label={`Remove ${name}`} onClick={onRemove}>
        <Trash2 className="size-4" aria-hidden />
      </Button>
    </div>
  );
}

function Text({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <Field label={label} htmlFor={id}>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function DateInput({
  id,
  label,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: string | null | undefined;
  disabled?: boolean;
  onChange: (value: string | null) => void;
}) {
  const invalid = Boolean(value && !MONTH.test(value));
  return (
    <Field label={label} htmlFor={id} hint={MONTH_HINT}>
      <Input
        id={id}
        inputMode="numeric"
        placeholder={disabled ? "" : "2023-03"}
        disabled={disabled}
        aria-invalid={invalid}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value.trim() || null)}
      />
    </Field>
  );
}
