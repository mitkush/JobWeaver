import { useState } from "react";
import { Link } from "react-router-dom";

import type { SavedAnswer, SavedAnswerInput } from "@/api/client";
import { useDeleteAnswer, useSaveAnswer, useSavedAnswers } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { WritingStyleCard } from "@/features/extension/WritingStyleCard";
import { COUNTRIES, countryName } from "@/lib/countries";

type Form = {
  question: string;
  answer: string;
  scope: "general" | "country" | "company";
  country: string;
  currency: string;
  period: "" | "year" | "month" | "hour";
  company_id: string | null;
  company_name: string;
  sensitive: boolean;
};

const BLANK: Form = {
  question: "",
  answer: "",
  scope: "general",
  country: "IN",
  currency: "",
  period: "",
  company_id: null,
  company_name: "",
  sensitive: false,
};

const PERIODS = { year: "per year", month: "per month", hour: "per hour" } as const;

function toForm(a: SavedAnswer): Form {
  return {
    question: a.question,
    answer: a.answer,
    scope: a.scope,
    country: a.country ?? "IN",
    currency: a.currency ?? "",
    period: a.period ?? "",
    company_id: a.company_id ?? null,
    company_name: a.company_name,
    sensitive: a.sensitive,
  };
}

function toInput(f: Form): SavedAnswerInput {
  const country = f.scope === "country";
  return {
    question: f.question,
    answer: f.answer,
    scope: f.scope,
    country: country ? f.country : null,
    currency: country && f.currency ? f.currency.toUpperCase() : null,
    period: country && f.period ? f.period : null,
    company_id: f.scope === "company" ? f.company_id : null,
    sensitive: f.sensitive,
  };
}

function scopeText(a: Pick<SavedAnswer, "scope" | "country" | "currency" | "period" | "company_name">): string {
  if (a.scope === "company") return `Only for ${a.company_name}`;
  if (a.scope === "country" && a.country) {
    const pay = a.currency && a.period ? `, ${a.currency} ${PERIODS[a.period]}` : "";
    return `Only for jobs in ${countryName(a.country)}${pay}`;
  }
  return "Any job";
}

/** Answers the extension may reuse on application forms, each only within its scope. */
export function SavedAnswersPage() {
  const answers = useSavedAnswers();
  const remove = useDeleteAnswer();
  const [editing, setEditing] = useState<{ id?: string; form: Form } | null>(null);
  const [deleting, setDeleting] = useState<SavedAnswer | null>(null);
  const toast = useToast();

  return (
    <>
      <PageHeader
        title="Saved answers"
        description="Answers to questions application forms keep asking. The extension reuses one only where it applies, and fills sensitive questions only from here."
        action={
          <div className="flex flex-wrap gap-2">
            <Link to="/settings" className={buttonClasses("ghost")}>
              Back to Settings
            </Link>
            <Button onClick={() => setEditing({ form: BLANK })}>Add answer</Button>
          </div>
        }
      />
      <div className="space-y-6">
        {editing && (
          <AnswerEditor
            key={editing.id ?? "new"}
            id={editing.id}
            initial={editing.form}
            onDone={(message) => {
              setEditing(null);
              if (message) toast("success", message);
            }}
          />
        )}
        {answers.isPending ? (
          <PageSpinner />
        ) : answers.isError ? (
          <Alert tone="error">{answers.error.message}</Alert>
        ) : answers.data.length === 0 ? (
          <Card>
            <CardBody>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                No saved answers yet. Add your notice period, salary expectation or work authorisation once, and the extension
                offers it on every form that asks.
              </p>
            </CardBody>
          </Card>
        ) : (
          <Card>
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {answers.data.map((answer) => (
                <li key={answer.id} className="flex flex-wrap items-start justify-between gap-3 p-5">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{answer.question}</p>
                    <p className="mt-1 text-sm whitespace-pre-line text-slate-700 dark:text-slate-300">{answer.answer}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Badge tone="neutral">{scopeText(answer)}</Badge>
                      {answer.sensitive && <Badge tone="warning">Sensitive</Badge>}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" onClick={() => setEditing({ id: answer.id, form: toForm(answer) })}>
                      Edit
                    </Button>
                    <Button variant="ghost" onClick={() => setDeleting(answer)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
        <WritingStyleCard />
      </div>
      <ConfirmDialog
        open={deleting !== null}
        title="Delete this saved answer?"
        confirmLabel="Delete"
        loading={remove.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await remove.mutateAsync(deleting.id);
          setDeleting(null);
          toast("success", "Saved answer deleted");
        }}
      >
        The extension stops offering it. Forms you already submitted are not affected.
      </ConfirmDialog>
    </>
  );
}

function AnswerEditor({ id, initial, onDone }: { id?: string; initial: Form; onDone: (message?: string) => void }) {
  const [form, setForm] = useState(initial);
  const save = useSaveAnswer();
  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const salaryHalf = form.scope === "country" && Boolean(form.currency) !== Boolean(form.period);
  const currencyBad = form.scope === "country" && form.currency !== "" && !/^[A-Za-z]{3}$/.test(form.currency);
  const valid = form.question.trim() && form.answer.trim() && !salaryHalf && !currencyBad;

  return (
    <Card>
      <CardHeader title={id ? "Edit answer" : "New answer"} />
      <CardBody className="space-y-4">
        <Field label="Question" htmlFor="a-question" hint="As forms ask it, for example: What is your notice period?">
          <Input id="a-question" value={form.question} onChange={(e) => set({ question: e.target.value })} />
        </Field>
        <Field label="Your answer" htmlFor="a-answer">
          <Textarea id="a-answer" value={form.answer} onChange={(e) => set({ answer: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Use it for" htmlFor="a-scope">
            <Select
              id="a-scope"
              value={form.scope}
              disabled={form.scope === "company"}
              onChange={(e) => set({ scope: e.target.value as Form["scope"] })}
            >
              <option value="general">Any job</option>
              <option value="country">Jobs in one country</option>
              {form.scope === "company" && <option value="company">Only {form.company_name}</option>}
            </Select>
          </Field>
          {form.scope === "country" && (
            <Field label="Country" htmlFor="a-country">
              <Select id="a-country" value={form.country} onChange={(e) => set({ country: e.target.value })}>
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {form.scope === "country" && (
            <Field label="Salary currency" htmlFor="a-currency" hint="Only for a salary answer, for example INR.">
              <Input
                id="a-currency"
                maxLength={3}
                value={form.currency}
                aria-invalid={currencyBad}
                onChange={(e) => set({ currency: e.target.value.toUpperCase() })}
              />
            </Field>
          )}
          {form.scope === "country" && (
            <Field label="Salary period" htmlFor="a-period">
              <Select id="a-period" value={form.period} onChange={(e) => set({ period: e.target.value as Form["period"] })}>
                <option value="">Not a salary</option>
                <option value="year">Per year</option>
                <option value="month">Per month</option>
                <option value="hour">Per hour</option>
              </Select>
            </Field>
          )}
        </div>
        {form.scope === "general" && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Answers for one Company are saved from the extension, on that Company&apos;s form.
          </p>
        )}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={form.sensitive} onChange={(e) => set({ sensitive: e.target.checked })} />
          <span>
            Sensitive: work authorisation, sponsorship, salary, notice period or a legal declaration. Questions like these are
            only ever filled from your saved answers, never written by AI.
          </span>
        </label>
        {salaryHalf && <p className="text-sm text-red-700 dark:text-red-400">A salary needs both a currency and a period.</p>}
        <div className="flex flex-wrap gap-2">
          <Button
            loading={save.isPending}
            disabled={!valid}
            onClick={async () => {
              try {
                await save.mutateAsync({ id, body: toInput(form) });
                onDone(id ? "Saved answer updated" : "Answer saved");
              } catch {
                // Shown below; the form stays open so nothing typed is lost.
              }
            }}
          >
            Save answer
          </Button>
          <Button variant="ghost" onClick={() => onDone()}>
            Cancel
          </Button>
        </div>
        {save.isError && <Alert tone="error">{save.error.message}</Alert>}
      </CardBody>
    </Card>
  );
}
