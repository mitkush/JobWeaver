import { Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { Preferences } from "@/api/client";
import { useSavePreferences } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChipInput } from "@/components/ui/chip-input";
import { Field, Input, Select } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import { COUNTRIES, countryName } from "@/lib/countries";

import { KeywordSettings } from "./KeywordSettings";
import { TitleSuggestions } from "./TitleSuggestions";
import { validatePreferences } from "./validate";

type WorkMode = Preferences["work_modes"][number];
const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "onsite", label: "Onsite (office)" },
  { value: "hybrid", label: "Hybrid (some days in office)" },
  { value: "remote", label: "Remote (WFH)" },
];

type FormValue = Preferences & {
  keywords: string[];
  core_keywords: string[];
  keyword_min_matches: number;
  search_keywords: boolean;
  locations: NonNullable<Preferences["locations"]>;
};
const EMPTY: FormValue = {
  titles: [],
  keywords: [],
  core_keywords: [],
  keyword_min_matches: 2,
  search_keywords: false,
  locations: [],
  work_modes: [],
};

export function PreferencesForm({
  initial,
  submitLabel = "Save preferences",
  onSaved,
}: {
  initial?: Preferences | null;
  submitLabel?: string;
  onSaved?: () => void;
}) {
  const [value, setValue] = useState<FormValue>(
    initial
      ? {
          ...EMPTY,
          ...initial,
          keywords: initial.keywords ?? [],
          core_keywords: initial.core_keywords ?? [],
          keyword_min_matches: initial.keyword_min_matches ?? 2,
          search_keywords: initial.search_keywords ?? false,
          locations: initial.locations ?? [],
        }
      : EMPTY,
  );
  const [locationScope, setLocationScope] = useState<"india" | "other" | "global">(
    initial?.locations?.length ? (initial.locations.some((l) => l.country === "IN") ? "india" : "other") : "global",
  );
  // The country picked under "Other country"; India always means IN.
  const [otherCountry, setOtherCountry] = useState(
    initial?.locations?.find((l) => l.country !== "IN")?.country ?? "US",
  );
  const country = locationScope === "india" ? "IN" : otherCountry;
  const [city, setCity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useSavePreferences();

  function addLocation() {
    const location = { country, city: city.trim() || null };
    const exists = value.locations.some(
      (l) => l.country === location.country && (l.city ?? "").toLowerCase() === (location.city ?? "").toLowerCase(),
    );
    if (!exists) setValue({ ...value, locations: [...value.locations, location] });
    setCity("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    // Global saves no places; the list stays in the form in case the User switches back.
    const nextValue =
      locationScope === "global"
        ? { ...value, locations: [] }
        : !value.locations.length
          ? { ...value, locations: [{ country, city: city.trim() || null }] }
          : value;
    const problem = validatePreferences(nextValue);
    setError(problem);
    if (problem) return;
    try {
      await save.mutateAsync(nextValue);
      if (locationScope !== "global") setValue(nextValue);
      onSaved?.();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <Field label="Job titles" htmlFor="titles" hint="Press Enter after each title. These drive which jobs are fetched.">
        <ChipInput
          id="titles"
          values={value.titles}
          onChange={(titles) => setValue({ ...value, titles })}
          placeholder="e.g. Backend Engineer"
        />
        <TitleSuggestions titles={value.titles} onAdd={(title) => setValue({ ...value, titles: [...value.titles, title] })} />
      </Field>

      <Field label="Keywords" htmlFor="keywords" hint="Optional. Skills or domains you want to be hired for, such as Ruby on Rails or fintech.">
        <ChipInput
          id="keywords"
          values={value.keywords}
          onChange={(keywords) =>
            setValue({
              ...value,
              keywords,
              // A removed keyword stops being core too.
              core_keywords: value.core_keywords.filter((c) => keywords.some((k) => k.toLowerCase() === c.toLowerCase())),
            })
          }
          placeholder="e.g. Python"
          max={30}
        />
      </Field>
      <KeywordSettings value={value} onChange={(next) => setValue({ ...value, ...next })} />

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-800 dark:text-slate-200">Locations</legend>
        <p className="text-xs text-slate-500 dark:text-slate-400">Choose job locations independently of work mode. Global includes all countries, including India.</p>
        <div className="flex flex-wrap gap-2">
          {([
            { value: "global", label: "Global (any country)" },
            { value: "india", label: "India" },
            { value: "other", label: "Other country" },
          ] as const).map((scope) => (
            <Button
              key={scope.value}
              variant={locationScope === scope.value ? "primary" : "secondary"}
              aria-pressed={locationScope === scope.value}
              onClick={() => {
                setLocationScope(scope.value);
                setCity("");
                setError(null);
              }}
            >
              {scope.label}
            </Button>
          ))}
        </div>
        {locationScope === "global" && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            No country or city selection needed.
            {value.locations.length > 0 && " Your places below are kept if you switch back to India or Other country."}
          </p>
        )}
        {value.locations.length > 0 && (
          <ul className={cn("flex flex-wrap gap-2", locationScope === "global" && "opacity-50")} aria-label="Places">
            {value.locations.map((location) => {
              const label = `${location.city ? `${location.city}, ` : ""}${countryName(location.country)}`;
              return (
                <li key={label} className="inline-flex items-center gap-1 rounded-full border border-slate-300 py-1 pl-3 pr-1 text-sm dark:border-slate-700">
                  {label}
                  <button
                    type="button"
                    aria-label={`Remove ${label}`}
                    className="rounded-full p-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => {
                      const locations = value.locations.filter((l) => l !== location);
                      setValue({ ...value, locations });
                    }}
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {locationScope !== "global" && (
          <>
            <p className="text-xs text-slate-500 dark:text-slate-400">Leave the city empty for the whole country. Use Add location for multiple places, or save your first selection directly.</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              {locationScope === "other" && (
                <Select value={otherCountry} onChange={(e) => setOtherCountry(e.target.value)} aria-label="Country" className="sm:w-56">
                  {COUNTRIES.filter((c) => c.code !== "IN").map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              )}
              <Input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addLocation();
                  }
                }}
                placeholder="City (optional)"
                aria-label="City"
              />
              <Button variant="secondary" onClick={addLocation}>
                <Plus className="size-4" aria-hidden />
                Add location
              </Button>
            </div>
          </>
        )}
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-slate-800 dark:text-slate-200">Work mode</legend>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">Remote means work from home. A job can list India or another location and still be Remote.</p>
        <div className="flex flex-wrap gap-2">
          {WORK_MODES.map(({ value: mode, label }) => {
            const active = value.work_modes.includes(mode);
            return (
              <button
                key={mode}
                type="button"
                aria-pressed={active}
                onClick={() =>
                  setValue({
                    ...value,
                    work_modes: active ? value.work_modes.filter((m) => m !== mode) : [...value.work_modes, mode],
                  })
                }
                className={cn(
                  "rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                  active
                    ? "border-brand-600 bg-brand-600 text-white"
                    : "border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
      </fieldset>

      {error && <Alert tone="error">{error}</Alert>}
      <Button type="submit" loading={save.isPending}>
        {submitLabel}
      </Button>
    </form>
  );
}
