import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Schemas } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";

import { WORK_MODES } from "./format";
import { clearFilters, hasFilters, withParam } from "./feed-params";

const WITHIN = [
  { value: "1", label: "Past 24 hours" },
  { value: "3", label: "Past 3 days" },
  { value: "7", label: "Past week" },
  { value: "30", label: "Past month" },
];

const TYPING_PAUSE_MS = 350;

export function FeedFilters({
  params,
  onChange,
  sources,
}: {
  params: URLSearchParams;
  onChange: (next: URLSearchParams) => void;
  sources: Schemas["SourceBadge"][];
}) {
  const [q, setQ] = useState(params.get("q") ?? "");
  const [location, setLocation] = useState(params.get("location") ?? "");
  // The latest URL state, so a delayed search never undoes a filter chosen meanwhile.
  const latest = useRef(params);
  useEffect(() => {
    latest.current = params;
  }, [params]);
  // Typed text is applied after a short pause, so each key press is not a request.
  useEffect(() => {
    const timer = setTimeout(() => {
      const current = latest.current;
      if (q.trim() !== (current.get("q") ?? "")) onChange(withParam(current, "q", q.trim() || null));
    }, TYPING_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [q, onChange]);
  useEffect(() => {
    const timer = setTimeout(() => {
      const current = latest.current;
      const value = location.trim();
      if (value !== (current.get("location") ?? "")) onChange(withParam(current, "location", value || null));
    }, TYPING_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [location, onChange]);

  return (
    <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-[2fr_1.2fr_1fr_1fr_1fr_auto]">
      <label className="relative block">
        <span className="sr-only">Search title or company</span>
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or company" className="pl-9" />
      </label>
      <label className="block">
        <span className="sr-only">Location</span>
        <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="City or country code" />
      </label>
      <label className="block">
        <span className="sr-only">Work mode</span>
        <Select value={params.get("work_mode") ?? ""} onChange={(e) => onChange(withParam(params, "work_mode", e.target.value || null))}>
          <option value="">Any work mode</option>
          {WORK_MODES.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </Select>
      </label>
      <label className="block">
        <span className="sr-only">Source</span>
        <Select value={params.get("source") ?? ""} onChange={(e) => onChange(withParam(params, "source", e.target.value || null))}>
          <option value="">Any source</option>
          {sources.map((source) => (
            <option key={source.name} value={source.name}>
              {source.label}
            </option>
          ))}
        </Select>
      </label>
      <label className="block">
        <span className="sr-only">Posted within</span>
        <Select value={params.get("within") ?? ""} onChange={(e) => onChange(withParam(params, "within", e.target.value || null))}>
          <option value="">Any date</option>
          {WITHIN.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </label>
      {hasFilters(params) && (
        <Button
          variant="ghost"
          onClick={() => {
            setQ("");
            setLocation("");
            onChange(clearFilters(params));
          }}
        >
          <X className="size-4" aria-hidden />
          Clear
        </Button>
      )}
    </div>
  );
}
