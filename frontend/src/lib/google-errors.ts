/** Readable text for the `google_error` reasons the OAuth callback returns. */
const MESSAGES: Record<string, string> = {
  cancelled: "Google sign-in was cancelled. You can try again whenever you are ready.",
  state: "That sign-in link was not started in this browser or has expired. Please start again.",
  google_failed: "Google did not finish signing you in. Please try again.",
  email_unverified: "Your Google email address is not verified yet. Verify it with Google, then try again.",
  gmail_scope: "Gmail access was not granted. On Google's screen, tick the box that allows JobWeaver to manage drafts.",
  gmail_account: "Connect Gmail with the same Google account you signed in with.",
  gmail_token: "Google did not return Gmail access. Please connect Gmail again.",
};

export function googleErrorMessage(reason: string | null): string | null {
  if (!reason) return null;
  return MESSAGES[reason] ?? MESSAGES.google_failed!;
}
