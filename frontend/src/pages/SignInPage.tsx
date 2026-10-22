import { Briefcase } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { api, unwrap } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { googleErrorMessage } from "@/lib/google-errors";

function DevLogin() {
  const [email, setEmail] = useState("dev@example.com");
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await unwrap(api.POST("/api/auth/dev-login", { body: { email, name: "Dev User" } }));
      window.location.assign("/");
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Local development only</p>
      <div className="flex gap-2">
        <Input value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Dev email" />
        <Button type="submit" variant="secondary" className="whitespace-nowrap">
          Dev sign-in
        </Button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  );
}

/** The hero's terminal: what one daily run looks like, as onebrain.run's agent loop. */
function RunPreview() {
  const lines = [
    ["ok", "fetched 1,284 postings from 9 sources"],
    ["ok", "grouped duplicates into 803 jobs"],
    ["ok", "matched 42 to your preferences"],
    ["ok", "skill gaps: 3 not in your fact bank"],
    ["..", "drafting resume for Backend Developer"],
    ["ok", "every line traced to a fact"],
  ];
  return (
    <div className="terminal w-full max-w-md" aria-hidden>
      <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <span className="size-2.5 rounded-full bg-red-400" />
        <span className="size-2.5 rounded-full bg-amber-400" />
        <span className="size-2.5 rounded-full bg-emerald-400" />
        <span className="ml-2 text-slate-500 dark:text-slate-400">~/jobweaver :: daily_run</span>
        <span className="ml-auto font-bold text-brand-600 dark:text-brand-400">● live</span>
      </div>
      <ul className="space-y-1.5 px-4 py-3 text-slate-700 dark:text-slate-300">
        {lines.map(([mark, text]) => (
          <li key={text}>
            <span className={mark === "ok" ? "text-emerald-600 dark:text-emerald-400" : "text-accent-700 dark:text-accent-300"}>
              {mark === "ok" ? "✓" : "›"}
            </span>{" "}
            {text}
          </li>
        ))}
      </ul>
      <div className="grid grid-cols-3 border-t border-slate-200 text-center dark:border-slate-800">
        {[["feed", "42"], ["drafts", "3"], ["applied", "17"]].map(([label, value]) => (
          <div key={label} className="border-r border-slate-200 py-2 last:border-r-0 dark:border-slate-800">
            <p className="text-[10px] tracking-[0.2em] text-slate-500 uppercase dark:text-slate-400">{label}</p>
            <p className="font-bold text-slate-900 dark:text-white">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SignInPage() {
  const [params] = useSearchParams();
  const next = params.get("next") ?? "/";
  const googleError = googleErrorMessage(params.get("google_error"));

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-display text-lg font-bold tracking-wide uppercase italic">
          <span className="clip-corner bg-brand-600 p-1.5 text-white dark:bg-brand-500 dark:text-slate-950">
            <Briefcase className="size-5" aria-hidden />
          </span>
          Job<span className="text-brand-600 dark:text-brand-500 neon-text">Weaver</span>
        </div>
        <p className="font-mono text-[11px] tracking-[0.18em] text-slate-500 uppercase dark:text-slate-400">
          sys//jobweaver <span className="text-emerald-600 dark:text-accent-300">online</span>
        </p>
      </div>
      <div className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <p className="eyebrow inline-block border border-brand-500/40 px-2 py-1">› jobweaver // every_genuine_job</p>
          <h1 className="mt-5 font-display text-5xl leading-[0.95] font-bold tracking-tight uppercase italic sm:text-6xl">
            Every genuine job,{" "}
            <span className="text-brand-600 dark:text-brand-500 neon-text">one card each.</span>
          </h1>
          <p className="mt-6 max-w-xl text-base text-slate-700 dark:text-slate-300">
            JobWeaver finds jobs across many sites, groups the duplicates, and prepares a{" "}
            <strong className="text-slate-900 dark:text-white">truthful, tailored application</strong> for each one.
            You review and send everything yourself.
          </p>
          <p className="mt-3 font-mono text-[11px] tracking-[0.14em] text-slate-500 uppercase dark:text-slate-400">
            // no invented skills · your gmail · you hit send
          </p>
          {googleError && (
            <Alert tone="warning" className="mt-6 max-w-xl">
              {googleError}
            </Alert>
          )}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href={`/api/auth/google/login?next=${encodeURIComponent(next)}`} className={buttonClasses("primary", "lg")}>
              Sign in with Google <span aria-hidden>→</span>
            </a>
          </div>
          <p className="mt-4 max-w-xl text-xs text-slate-500 dark:text-slate-400">
            While JobWeaver is in testing, Google only lets accounts the owner has added sign in.
            If Google blocks you, ask the owner to add your Gmail address.
          </p>
          {import.meta.env.DEV && (
            <Card className="mt-6 max-w-xl">
              <CardBody className="py-4">
                <DevLogin />
              </CardBody>
            </Card>
          )}
        </div>
        <div className="flex justify-center lg:justify-end">
          <RunPreview />
        </div>
      </div>
    </div>
  );
}
