import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/field";

import type { Content, Line, Part, Version } from "./api";

const SECTIONS: NonNullable<Line["section"]>[] = ["Headline", "Contact", "Summary", "Skills", "Experience", "Projects", "Education", "Links", "Additional"];

export function DraftEditor({ content, part, facts, onChange, disabled }: {
  content: Content; part: Part; facts: Version["facts"]; onChange: (content: Content) => void; disabled: boolean;
}) {
  const [factToAdd, setFactToAdd] = useState(facts[0]?.ref ?? "");
  const [citationToAdd, setCitationToAdd] = useState<Record<string, string>>({});
  const lines = content[part] ?? [];
  const update = (next: Line[]) => onChange({ ...content, [part]: next });
  const citationFor = (line: Line, index: number) => {
    const selected = citationToAdd[line.id ?? String(index)];
    return selected && !line.fact_refs.includes(selected) ? selected : facts.find((fact) => !line.fact_refs.includes(fact.ref))?.ref ?? "";
  };
  const move = (index: number, offset: number) => {
    const next = [...lines];
    const here = next[index];
    const there = next[index + offset];
    if (!here || !there) return;
    next[index] = there;
    next[index + offset] = here;
    update(next);
  };
  return (
    <div className="space-y-4">
      {lines.map((line, index) => (
        <div key={line.id ?? index} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            {part === "resume" && <Select aria-label={`Section for line ${index + 1}`} value={line.section ?? "Experience"} disabled={disabled} className="w-40" onChange={(event) => update(lines.map((entry, i) => i === index ? { ...entry, section: event.target.value as Line["section"] } : entry))}>
              {SECTIONS.map((section) => <option key={section}>{section}</option>)}
            </Select>}
            {part === "resume" && (line.section === "Skills" || line.section === "Experience" || line.section === "Projects" || line.section === "Education") && <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
              <input type="checkbox" checked={line.heading ?? false} disabled={disabled} onChange={(event) => update(lines.map((entry, i) => i === index ? { ...entry, heading: event.target.checked } : entry))} />
              Title line
            </label>}
            <div className="flex gap-1">
              {line.manual && <span className="self-center text-xs text-slate-500 dark:text-slate-400">Your edit</span>}
              <Button size="sm" variant="ghost" aria-label={`Move line ${index + 1} up`} disabled={disabled || index === 0} onClick={() => move(index, -1)}><ArrowUp className="size-4" /></Button>
              <Button size="sm" variant="ghost" aria-label={`Move line ${index + 1} down`} disabled={disabled || index === lines.length - 1} onClick={() => move(index, 1)}><ArrowDown className="size-4" /></Button>
              <Button size="sm" variant="ghost" aria-label={`Remove line ${index + 1}`} disabled={disabled || (part !== "email_body" && lines.length === 1)} onClick={() => update(lines.filter((_, i) => i !== index))}><Trash2 className="size-4" /></Button>
            </div>
          </div>
          <Textarea aria-label={`Draft line ${index + 1}`} value={line.text} disabled={disabled} rows={3} onChange={(event) => update(lines.map((entry, i) => i === index ? { ...entry, text: event.target.value } : entry))} />
          <details className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            <summary className="cursor-pointer font-medium">Tailoring Trace ({line.fact_refs.length} Facts)</summary>
            <div className="mt-2 space-y-2">
              {facts.filter((fact) => line.fact_refs.includes(fact.ref)).map((fact) => <div key={fact.ref} className="flex items-start justify-between gap-2"><p><strong>{fact.ref} · {fact.group || fact.kind}</strong> · {fact.in_base_resume ? "Base Resume" : "Fact Bank addition"}<br />{fact.text}</p><Button size="sm" variant="ghost" aria-label={`Remove citation ${fact.ref} from line ${index + 1}`} disabled={disabled || line.fact_refs.length <= 1} onClick={() => update(lines.map((entry, i) => i === index ? { ...entry, fact_refs: entry.fact_refs.filter((ref) => ref !== fact.ref) } : entry))}>Remove</Button></div>)}
              {facts.some((fact) => !line.fact_refs.includes(fact.ref)) && <div className="flex flex-wrap items-center gap-2"><Select aria-label={`Fact to cite for line ${index + 1}`} value={citationFor(line, index)} disabled={disabled} onChange={(event) => setCitationToAdd({ ...citationToAdd, [line.id ?? String(index)]: event.target.value })}>{facts.filter((fact) => !line.fact_refs.includes(fact.ref)).map((fact) => <option key={fact.ref} value={fact.ref}>{fact.ref}: {fact.text.slice(0, 90)}</option>)}</Select><Button size="sm" variant="secondary" disabled={disabled || line.fact_refs.length >= 20} onClick={() => { const ref = citationFor(line, index); if (ref) update(lines.map((entry, i) => i === index ? { ...entry, fact_refs: [...entry.fact_refs, ref] } : entry)); }}>Cite Fact</Button></div>}
            </div>
          </details>
        </div>
      ))}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select aria-label="Fact to add" value={factToAdd} onChange={(event) => setFactToAdd(event.target.value)} disabled={disabled}>
          {facts.map((fact) => <option key={fact.ref} value={fact.ref}>{fact.ref}: {fact.text.slice(0, 90)}</option>)}
        </Select>
        <Button variant="secondary" disabled={disabled || !factToAdd} onClick={() => {
          const fact = facts.find((entry) => entry.ref === factToAdd);
          if (fact) update([...lines, { id: crypto.randomUUID(), text: fact.text, fact_refs: [fact.ref], section: fact.group === "Contact" ? "Contact" : fact.kind === "skill" ? "Skills" : fact.kind === "project" ? "Projects" : fact.kind === "education" ? "Education" : "Experience", manual: true }]);
        }}>Add Fact</Button>
      </div>
    </div>
  );
}
