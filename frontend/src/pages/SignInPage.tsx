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
    <form onSubmit={submit} className="mt-6 space-y-2 border-t border-dashed border-slate-300 pt-4 dark:border-slate-700">
      <p className="text-xs font-medium text-slate-500">Local development only</p>
      <div className="flex gap-2">
        <Input value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Dev email" />
        <Button type="submit" variant="secondary">
          Dev sign-in
        </Button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  );
}

export function SignInPage() {
  const [params] = useSearchParams();
  const next = params.get("next") ?? "/";
  const googleError = googleErrorMessage(params.get("google_error"));

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardBody className="py-8">
          <div className="flex items-center gap-2 text-lg font-semibold">
            <span className="rounded-md bg-brand-600 p-1.5 text-white">
              <Briefcase className="size-5" aria-hidden />
            </span>
            JobWeaver
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight">Every genuine job, one card each.</h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            JobWeaver finds jobs across many sites, groups the duplicates, and prepares a truthful,
            tailored application for each one. You review and send everything yourself.
          </p>
          {googleError && (
            <Alert tone="warning" className="mt-6">
              {googleError}
            </Alert>
          )}
          <a
            href={`/api/auth/google/login?next=${encodeURIComponent(next)}`}
            className={buttonClasses("primary", "lg") + " mt-6 w-full"}
          >
            Sign in with Google
          </a>
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            While JobWeaver is in testing, Google only lets accounts the owner has added sign in.
            If Google blocks you, ask the owner to add your Gmail address.
          </p>
          {import.meta.env.DEV && <DevLogin />}
        </CardBody>
      </Card>
    </div>
  );
}
