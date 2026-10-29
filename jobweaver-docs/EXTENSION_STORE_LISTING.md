# Chrome Web Store listing

What to enter when publishing the extension (ADR-0017). Submission is a release action
done in the publisher's developer account; this repo only prepares the package and text.
Keep it in step with `extension/manifest.ts` and `/privacy/extension`.

## Package

1. `cd extension && npm ci && npm run build:store` (production server by default; set
   `JOBWEAVER_ORIGIN` for another HTTPS server). Upload
   `extension/release/jobweaver-extension-<version>.zip`.
2. After the first upload the dashboard shows the store's extension ID. Add it to
   `EXTENSION_IDS` on the server next to `npdbpfgligiimfnoblngghbokehjbafm` (unpacked
   installs keep working), and restart the server.
3. Once the listing is live, set `EXTENSION_STORE_URL` to its address so Settings shows
   **Get the extension**.
4. Each update: raise `version` in `extension/package.json`, rebuild, upload.

Visibility: **Unlisted** (only people with the link can install) until JobWeaver opens
beyond private use (ADR-0012).

## Listing

- **Name:** JobWeaver
- **Summary (132 characters max):** Fills job application forms from your JobWeaver Drafts. You review every value and submit the form yourself.
- **Category:** Workflow & Planning
- **Description:**

  JobWeaver fills job application forms from the profile, resume and cover letter you
  prepared in JobWeaver.

  Open it in the side panel on an application form, choose your Draft for that job and
  scan the form. JobWeaver shows what it would put in each field; untick anything you do
  not want, then fill. Your tailored resume and cover letter PDFs are attached for you.
  Undo puts the form back.

  For the form's own questions it offers your saved answer, or a suggestion written only
  from the facts in your JobWeaver Fact Bank, for you to rework before using. Questions
  about work authorisation, salary or notice period are answered only from answers you
  saved yourself, and forms that ask for answers not written by AI get notes instead.

  JobWeaver never submits a form or clicks Next. You check the page and submit it
  yourself, then mark the application as applied.

  Requires a JobWeaver account.

- **Icon:** `extension/public/icons/icon-128.png`
- **Screenshots (1280x800):** the side panel on a form after a scan; the question
  suggestions; the fill report with Undo. Use a test account and a fixture form, never a
  real person's data.
- **Privacy policy URL:** `https://<server>/privacy/extension`
- **Homepage URL:** `https://<server>/`

## Single purpose

Fills job application forms from the user's own JobWeaver profile and documents, for
the user to review and submit.

## Permission justifications

| Permission | Why |
| --- | --- |
| `storage` | Keeps the JobWeaver connection and unfinished review in session storage, cleared when the browser closes. |
| `activeTab` | Reads and fills the form on the tab where the user clicked the toolbar button, only then. |
| `scripting` | Runs the form scanner and filler in that tab, on the user's click. |
| `sidePanel` | Shows the extension beside the form, so the user can compare values with the page. |
| Host: the JobWeaver server | Talks to the user's JobWeaver account. |
| Optional host: `https://*/*`, `http://*/*` | Requested one site at a time when the user chooses Allow access to that site, for example an application form opened in a new tab. Never granted at install. |
| Optional `webNavigation` | Requested when the user chooses Find embedded forms, to list the frames on the current tab. |
| Optional `downloads` | Requested when the user chooses Save PDFs in company folder. |

Remote code: **No.** All code is in the package; the extension fetches only data from
the JobWeaver server.

## Data use (privacy practices tab)

Collected or handled:

- **Personally identifiable information:** the user's name, email, phone, location and
  links from their JobWeaver profile, written into forms they choose to fill.
- **Authentication information:** the extension's own JobWeaver access credential, kept
  in session storage.
- **Website content:** a job advert's text when the user reads it, and form question
  labels when the user asks for suggested answers, sent to the user's JobWeaver account.

Not collected: health, financial and payment information, personal communications,
location from the browser, web history, user activity such as clicks or keystrokes.

Certify all three: data is not sold to third parties; not used or transferred for purposes
unrelated to the single purpose; not used or transferred to determine creditworthiness or
for lending.
