import { useState } from "react";

import { ApiError, type FollowUp, type Reminder } from "@/api/client";
import { useFollowUp, useSendFollowUp } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { gmailConnectHref } from "@/features/gmail/links";

const WARNING_PREFIX = "Confirm the email warning before continuing: ";

/** Follow-up email (FR-F2): a template the User edits, placed in Gmail Drafts, never sent. */
export function FollowUpDialog({ reminder, onClose }: { reminder: Reminder; onClose: () => void }) {
  const template = useFollowUp(reminder.application_id);
  if (template.data) return <FollowUpForm reminder={reminder} template={template.data} onClose={onClose} />;
  return (
    <ConfirmDialog
      open
      title={`Follow up with ${reminder.company}`}
      confirmLabel="Open in Gmail"
      tone="primary"
      confirmDisabled
      onConfirm={() => undefined}
      onCancel={onClose}
    >
      {template.isError ? (
        <Alert tone="error">{(template.error as Error).message}</Alert>
      ) : (
        <Spinner label="Preparing your follow-up" />
      )}
    </ConfirmDialog>
  );
}

function FollowUpForm({ reminder, template, onClose }: { reminder: Reminder; template: FollowUp; onClose: () => void }) {
  const send = useSendFollowUp();
  const toast = useToast();
  const [recipient, setRecipient] = useState(template.recipient ?? "");
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const [warning, setWarning] = useState<string | null>(null);
  const [acceptWarning, setAcceptWarning] = useState(false);
  const [reconnect, setReconnect] = useState(false);

  async function submit() {
    try {
      const result = await send.mutateAsync({
        id: reminder.application_id,
        body: { recipient, subject, body, confirm: true, confirm_email_warning: acceptWarning },
      });
      toast("success", result.message);
      window.open(result.url, "_blank", "noopener");
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.message.startsWith(WARNING_PREFIX)) {
        setWarning(error.message.slice(WARNING_PREFIX.length));
      } else if (error instanceof ApiError && error.code === "gmail_expired") {
        setReconnect(true);
      } else {
        toast("error", (error as Error).message);
      }
    }
  }

  const ready = recipient.trim() && subject.trim() && body.trim();
  return (
    <ConfirmDialog
      open
      title={`Follow up with ${reminder.company}`}
      confirmLabel="Open in Gmail"
      tone="primary"
      loading={send.isPending}
      confirmDisabled={!ready || (warning !== null && !acceptWarning)}
      onConfirm={() => void submit()}
      onCancel={onClose}
    >
      <div className="space-y-4">
        <p>This creates a draft in your Gmail Drafts. Nothing is sent: review and send it from Gmail.</p>
        <Field label="To" htmlFor="follow-up-to">
          <Input
            id="follow-up-to"
            type="email"
            value={recipient}
            onChange={(e) => {
              setRecipient(e.target.value);
              setWarning(null);
              setAcceptWarning(false);
            }}
            required
          />
        </Field>
        <Field label="Subject" htmlFor="follow-up-subject">
          <Input id="follow-up-subject" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} />
        </Field>
        <Field label="Message" htmlFor="follow-up-body">
          <Textarea id="follow-up-body" rows={9} value={body} onChange={(e) => setBody(e.target.value)} maxLength={5000} />
        </Field>
        {warning && (
          <Alert tone="warning" title="Check this address">
            <p>{warning}</p>
            <label className="mt-2 flex items-center gap-2">
              <input type="checkbox" checked={acceptWarning} onChange={(e) => setAcceptWarning(e.target.checked)} />
              Use this address anyway
            </label>
          </Alert>
        )}
        {reconnect && (
          <Alert
            tone="warning"
            action={
              <a className={buttonClasses("secondary", "sm")} href={gmailConnectHref("/applications")}>
                Reconnect Gmail
              </a>
            }
          >
            Gmail access ended. Reconnect, then open the follow-up again.
          </Alert>
        )}
      </div>
    </ConfirmDialog>
  );
}
