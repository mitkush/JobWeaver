# JobWeaver never sends; the User sends from Gmail

Nothing leaves JobWeaver on its own. "Save draft" only saves. The outward action is **Open in Gmail**: JobWeaver creates a real Gmail draft with the Tailored Resume attached (Gmail API, `gmail.compose` scope), and the User reviews, reformats and sends it inside Gmail. The Google OAuth app runs in testing mode (up to 100 named test users, no Google verification); its refresh tokens expire about every 7 days, so JobWeaver detects expiry and shows a re-login reminder. If the Gmail API is unavailable, the fallback is a Gmail compose link with recipient, subject and body pre-filled, and the PDF attached by hand (compose links cannot carry attachments).

**Considered and rejected:** sending directly via `gmail.send` (removes the User's final check in their own mail client), compose-link only (no attachment, more manual work on every application), reading replies to automate the tracker (needs a further restricted scope; out of V1).

**Consequences:** `gmail.compose` is restricted, so a public launch needs Google verification and a security assessment (recorded as a pre-launch item, not a V1 task); Gmail tokens are encrypted at rest; the scope classification and the 7-day expiry must be confirmed against Google's documentation before build.
