import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DraftEditor } from "./DraftEditor";
import type { Content, Part, Version } from "./api";

export function DocumentReview({ content, part, facts, onChange, disabled, onSection }: {
  content: Content; part: Part; facts: Version["facts"]; onChange: (content: Content) => void;
  disabled: boolean; onSection: (section: Content["resume"][number]["section"] | undefined) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const groups = part === "resume" ? [...new Set(content.resume.map(line => line.section ?? "Experience"))] : [part];
  const lines = content[part] ?? [];
  const sectionLines = editing && part === "resume" ? content.resume.filter(line => (line.section ?? "Experience") === editing) : lines;
  return <div className="space-y-4">
    {editing ? <>
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Editing {editing.replaceAll("_", " ")}</h2><Button variant="secondary" onClick={() => { setEditing(null); onSection(undefined); }}>Done editing</Button></div>
      <DraftEditor content={{ ...content, [part]: sectionLines }} part={part} facts={facts} disabled={disabled} onChange={(updated) => {
        if (part !== "resume") { onChange(updated); return; }
        const index = content.resume.findIndex(line => (line.section ?? "Experience") === editing);
        const kept = content.resume.filter(line => (line.section ?? "Experience") !== editing);
        onChange({ ...content, resume: [...kept.slice(0, index), ...updated.resume, ...kept.slice(index)] });
      }} />
    </> : <article aria-label="Readable document preview" className="mx-auto max-w-prose space-y-6 bg-white p-5 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {groups.map(group => <section key={group}>
        <div className="mb-3 flex items-center justify-between gap-3"><h2 className="font-semibold">{group.replaceAll("_", " ")}</h2><Button size="sm" variant="ghost" onClick={() => { setEditing(group); onSection(part === "resume" ? group as Content["resume"][number]["section"] : undefined); }}>Edit {group.replaceAll("_", " ")}</Button></div>
        <div className="space-y-2 leading-7">{lines.filter(line => part !== "resume" || (line.section ?? "Experience") === group).map(line => <p key={line.id} className={line.heading ? "font-semibold" : ""}>{line.text}</p>)}</div>
      </section>)}
    </article>}
  </div>;
}
