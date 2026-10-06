import { Check } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";

import type { Me } from "@/api/client";
import { useAcceptNotice, useDocuments, useFacts, usePreferences, useReviewFactBank, useSetCountry } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/field";
import { PageSpinner } from "@/components/ui/spinner";
import { DocumentUploader } from "@/features/fact-bank/DocumentUploader";
import { FactBankEditor } from "@/features/fact-bank/FactBankEditor";
import { GmailCard } from "@/features/gmail/GmailCard";
import { PreferencesForm } from "@/features/preferences/PreferencesForm";
import { cn } from "@/lib/cn";
import { COUNTRIES } from "@/lib/countries";
import { googleErrorMessage } from "@/lib/google-errors";

import { furthestStep, index, STEPS, type StepKey } from "./onboarding-steps";

function Stepper({ current, furthest }: { current: StepKey; furthest: StepKey }) {
  return (
    <ol className="mb-8 flex flex-wrap gap-x-6 gap-y-2" aria-label="Setup progress">
      {STEPS.map((step, i) => {
        const done = i < index(furthest) && step.key !== current;
        const active = step.key === current;
        return (
          <li key={step.key} className="flex items-center gap-2 text-sm" aria-current={active ? "step" : undefined}>
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full border text-xs font-semibold",
                active && "border-brand-600 bg-brand-600 text-white",
                done && "border-emerald-600 bg-emerald-600 text-white",
                !active && !done && "border-slate-300 text-slate-500 dark:border-slate-700",
              )}
            >
              {done ? <Check className="size-3.5" aria-hidden /> : i + 1}
            </span>
            <span className={cn(active ? "font-medium" : "text-slate-500 dark:text-slate-400")}>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function NoticeStep() {
  const accept = useAcceptNotice();
  const navigate = useNavigate();
  return (
    <Card>
      <CardHeader title="How your documents are used" />
      <CardBody className="space-y-4 text-sm">
        <p>
          JobWeaver reads your resume and portfolio with free AI services (Google Gemini, Groq and
          OpenRouter) to build your Fact Bank and, later, to tailor applications. On their free tiers,
          these providers may use what is sent to them to improve their products.
        </p>
        <p className="text-slate-600 dark:text-slate-400">
          Nothing is sent to any AI provider until you accept. You can delete your documents and
          your account at any time.
        </p>
        <Button
          loading={accept.isPending}
          onClick={async () => {
            await accept.mutateAsync();
            navigate("/onboarding/country");
          }}
        >
          I understand, continue
        </Button>
        {accept.isError && <Alert tone="error">{accept.error.message}</Alert>}
      </CardBody>
    </Card>
  );
}

function CountryStep({ me }: { me: Me }) {
  const [country, setCountry] = useState(me.country ?? "IN");
  const save = useSetCountry();
  const navigate = useNavigate();
  return (
    <Card>
      <CardHeader title="Where are you based?" description="Some AI terms depend on where you live." />
      <CardBody className="space-y-4">
        <Field label="Country" htmlFor="country">
          <Select id="country" value={country} onChange={(e) => setCountry(e.target.value)} className="sm:w-72">
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        {me.onboarding.ai_region_blocked && (
          <Alert tone="warning" title="Not available in your region yet">
            Google's free AI terms do not allow serving people in the EEA, Switzerland or the UK.
            JobWeaver will open for your region once it moves to paid AI.
          </Alert>
        )}
        <Button
          loading={save.isPending}
          onClick={async () => {
            const me = await save.mutateAsync(country);
            if (!me.onboarding.ai_region_blocked) navigate("/onboarding/documents");
          }}
        >
          Continue
        </Button>
      </CardBody>
    </Card>
  );
}

function DocumentsStep() {
  const documents = useDocuments();
  const navigate = useNavigate();
  if (!documents.data) return <PageSpinner />;
  const hasResume = documents.data.some((d) => d.kind === "resume");
  return (
    <Card>
      <CardHeader
        title="Add your documents"
        description="Your Fact Bank is built only from these. Tailored resumes can never claim anything that is not in them."
      />
      <CardBody className="space-y-4">
        <DocumentUploader documents={documents.data} />
        <Button disabled={!hasResume} onClick={() => navigate("/onboarding/review")}>
          Continue to review
        </Button>
        {!hasResume && <p className="text-xs text-slate-500">Upload your resume to continue.</p>}
      </CardBody>
    </Card>
  );
}

function ReviewStep() {
  const facts = useFacts();
  const review = useReviewFactBank();
  const navigate = useNavigate();
  if (!facts.data) return <PageSpinner />;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Check your Fact Bank"
          description="Fix anything the AI misread, merge duplicates and add what is missing. Facts marked “Not in your resume” came from your portfolio."
        />
      </Card>
      <FactBankEditor facts={facts.data} />
      {review.isError && <Alert tone="error">{review.error.message}</Alert>}
      <Button
        size="lg"
        disabled={!facts.data.length}
        loading={review.isPending}
        onClick={async () => {
          await review.mutateAsync();
          navigate("/onboarding/preferences");
        }}
      >
        These Facts are correct
      </Button>
    </div>
  );
}

function PreferencesStep() {
  const preferences = usePreferences();
  const navigate = useNavigate();
  if (preferences.isPending) return <PageSpinner />;
  return (
    <Card>
      <CardHeader title="What are you looking for?" description="You can change this any time; the Feed follows it." />
      <CardBody>
        <PreferencesForm
          initial={preferences.data}
          submitLabel="Save and continue"
          onSaved={() => navigate("/onboarding/gmail")}
        />
      </CardBody>
    </Card>
  );
}

function GmailStep({ me }: { me: Me }) {
  const [params] = useSearchParams();
  return (
    <Card>
      <CardHeader title="Connect Gmail (optional)" description="You can do this later in Settings." />
      <CardBody className="space-y-5">
        {params.get("gmail") === "connected" && <Alert tone="success">Gmail is connected.</Alert>}
        {params.get("google_error") && <Alert tone="warning">{googleErrorMessage(params.get("google_error"))}</Alert>}
        <GmailCard me={me} next="/onboarding/gmail" />
        <a href="/feed" className={buttonClasses(me.onboarding.gmail_connected ? "primary" : "secondary")}>
          {me.onboarding.gmail_connected ? "Go to my Feed" : "Skip for now"}
        </a>
      </CardBody>
    </Card>
  );
}

export function OnboardingPage({ me }: { me: Me }) {
  const { step } = useParams<{ step?: StepKey }>();
  const furthest = furthestStep(me);
  if (!step || !STEPS.some((s) => s.key === step) || index(step) > index(furthest)) {
    return <Navigate to={`/onboarding/${furthest}`} replace />;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Set up JobWeaver</h1>
      <p className="mb-6 text-sm text-slate-600 dark:text-slate-400">
        A few minutes now, so every application later is sharper and truthful.
      </p>
      <Stepper current={step} furthest={furthest} />
      {step === "notice" && <NoticeStep />}
      {step === "country" && <CountryStep me={me} />}
      {step === "documents" && <DocumentsStep />}
      {step === "review" && <ReviewStep />}
      {step === "preferences" && <PreferencesStep />}
      {step === "gmail" && <GmailStep me={me} />}
    </div>
  );
}
