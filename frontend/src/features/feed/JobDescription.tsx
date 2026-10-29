/** Read source text safely. Formatting never rewrites the requirements or executes HTML. */
export function JobDescription({ text }: { text: string }) {
  if (!text.trim()) return <p>No description was provided.</p>;
  const blocks = text.replace(/\r\n?/g, "\n").split(/\n+/).map(line => line.trim()).filter(Boolean);
  const output: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) { output.push(<ul key={`list-${output.length}`} className="list-disc space-y-2 pl-6">{bullets.map((line, i) => <li key={i}>{line}</li>)}</ul>); bullets = []; }
  };
  for (const line of blocks) {
    if (/^(?:[-*•▪]|\d+[.)])\s+/.test(line)) { bullets.push(line.replace(/^(?:[-*•▪]|\d+[.)])\s+/, "")); continue; }
    flush();
    const heading = line.length < 100 && (/^(?:about (?:us|the (?:role|job|company))|responsibilities|(?:key |your )?responsibilities|(?:minimum |preferred )?(?:qualifications|requirements)|what (?:you|we)|benefits|skills|how to apply|equal opportunity)/i.test(line) || /^#{1,4}\s/.test(line));
    output.push(heading ? <h3 key={output.length} className="pt-3 text-lg font-semibold text-slate-950 dark:text-white">{line.replace(/^#{1,4}\s+/, "")}</h3> : <p key={output.length}>{line}</p>);
  }
  flush();
  return <article aria-label="Full job description" className="max-w-prose space-y-4 break-words text-base leading-7 text-slate-700 dark:text-slate-200">{output}</article>;
}
