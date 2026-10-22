import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { Input } from "./field";

export function ChipInput({
  id,
  values,
  onChange,
  placeholder,
  max = 20,
}: {
  id: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  max?: number;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const value = draft.trim().replace(/\s+/g, " ");
    if (value && !values.some((v) => v.toLowerCase() === value.toLowerCase()) && values.length < max) {
      onChange([...values, value]);
    }
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      add();
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className="space-y-2">
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Added">
          {values.map((value) => (
            <li
              key={value}
              className="inline-flex items-center gap-1 rounded-sm bg-brand-50 py-1 pr-1 pl-2.5 text-sm text-brand-700 ring-1 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-200 dark:ring-brand-500/40"
            >
              {value}
              <button
                type="button"
                onClick={() => onChange(values.filter((v) => v !== value))}
                className="rounded-sm p-0.5 hover:bg-brand-100 dark:hover:bg-brand-500/25"
                aria-label={`Remove ${value}`}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Input
        id={id}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
    </div>
  );
}
