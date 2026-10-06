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

import { validatePreferences } from "./validate";

type WorkMode = Preferences["work_modes"][number];
const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
];

type FormValue = Preferences & { keywords: string[] };
const EMPTY: FormValue = { titles: [], keywords: [], locations: [], work_modes: [] };

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
    initial ? { ...initial, keywords: initial.keywords ?? [] } : EMPTY,
  );
  const [country, setCountry] = useState("IN");
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
    const problem = validatePreferences(value);
    setError(problem);
    if (problem) return;
    try {
      await save.mutateAsync(value);
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
      </Field>

      <Field label="Keywords" htmlFor="keywords" hint="Optional. Technologies or domains you want, such as FastAPI or fintech.">
        <ChipInput
          id="keywords"
          values={value.keywords}
          onChange={(keywords) => setValue({ ...value, keywords })}
          placeholder="e.g. Python"
          max={30}
        />
      </Field>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-800 dark:text-slate-200">Locations</legend>
        <p className="text-xs text-slate-500 dark:text-slate-400">Leave the city empty to include the whole country.</p>
        {value.locations.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {value.locations.map((location) => {
              const label = `${location.city ? `${location.city}, ` : ""}${countryName(location.country)}`;
              return (
                <li key={label} className="inline-flex items-center gap-1 rounded-full border border-slate-300 py-1 pl-3 pr-1 text-sm dark:border-slate-700">
                  {label}
                  <button
                    type="button"
                    aria-label={`Remove ${label}`}
                    className="rounded-full p-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => setValue({ ...value, locations: value.locations.filter((l) => l !== location) })}
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country" className="sm:w-56">
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </Select>
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
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-slate-800 dark:text-slate-200">Work mode</legend>
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
