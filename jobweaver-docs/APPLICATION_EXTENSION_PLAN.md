# Application form extension plan

Status: proposed, for review in a draft PR. Decisions are recorded in ADR-0017 and FR-E14.
This document adds no extension, endpoint, permission, migration or deployment change. The
stages below are implementation proposals, not promises that a particular third-party form
already works.

## Goal and first release

Help a User apply to a Job on any careers site or application form: fill the form from
reviewed information and a selected saved Draft version, attach the Tailored Resume, and
suggest answers to the form's own questions. The User reviews everything on the employer's
page and submits it themselves, then explicitly marks the Application Applied. The extension
never submits, never clicks Next and never applies in bulk (PRD non-goal: not an auto-apply
bot).

Start with an unpacked Manifest V3 extension for Chrome and Brave on desktop. It works on
any site through a generic field mapper. Greenhouse, Lever and Ashby get dedicated form
adapters because they cover most apply links in the Feed and their layouts are stable; a
dedicated adapter is a higher-confidence mapping, not a prerequisite. Fields the mapper
cannot identify stay visible as manual work.

Outside the first release: automatic submission or Next-button clicks, bulk applications,
LinkedIn Easy Apply, Workday account creation, CAPTCHA handling, scraping Jobs in the
background and public extension-store distribution. Adding an application form adapter is
separate from adding a Source Adapter.

## User flow

1. On any page with a job advert or application form, click the extension and connect
   JobWeaver if necessary.
2. The extension suggests the Job by matching the page URL against stored apply links.
   URL matching may suggest a Job, but cannot silently select an ambiguous match.
   - **Known Job:** show Company, title, destination hostname, the saved Draft version
     and its save time, or a Create Draft action.
   - **Unknown Job:** offer Capture this job. The extension reads the advert from the
     page (JSON-LD `JobPosting` when present, otherwise the visible text or the User's
     selection), shows it for review and sends it to JobWeaver as a Captured Job
     (ADR-0017). The User then creates the Draft.
3. Tailoring, checks and edits happen on JobWeaver's Draft page, which the extension opens.
   The popup shows the Draft's state, its warning count and the version that will be used.
   Unsaved edits must be saved before that version can be used.
4. Scan the current form on demand. Preview each proposed field, its value and its source:
   profile, Saved Answer, Draft, Fact notes or AI suggestion. Allow selection of individual
   fields. Existing nonempty fields are skipped by default; overwriting requires a separate
   explicit selection.
5. Click Fill selected fields. Report filled, skipped and failed fields separately, and
   outline them on the page: exact data, needs review (AI suggestion), left empty.
   Preserve existing input on errors and rescan after a page transition when requested.
6. Attach the selected Tailored Resume and Cover Letter to matching file inputs, using
   JobWeaver's existing PDF generation. Display the exact version and file name so a newer
   Draft cannot silently replace the selected PDF. If a site rejects programmatic
   attachment, download the file and ask the User to attach it.
7. Review and submit on the employer's site. A separate I submitted this application action
   updates the Application through JobWeaver. Filling fields or detecting a confirmation
   page alone does not mark it Applied.

## Questions on the form

Fields that are not profile data (for example "Why do you want to work here?" or "Years of
experience with Rails") are sent to JobWeaver as question text only: label, field type,
options and whether it is required. Never page HTML, other field values or the full URL.
JobWeaver answers each one through a typed AI Gateway task, after the AI notice and region
checks (ADR-0007, ADR-0012), with one of:

- **Saved Answer:** reuse what the User saved for the same question before.
- **Suggestion:** a complete answer ready to edit, not a fragment, written only from the
  User's Facts with a Tailoring Trace (ADR-0005) and in the User's Writing Style. Its length
  follows the field: a sentence for a single-line input, one or two full paragraphs for a
  text area, and never more than a word or character limit stated on the form or set by
  `maxlength`. Never auto-accepted; outlined as needs review for the User to rework.
- **Fact notes:** the relevant Facts as short notes beside the field, with no prose.
- **Leave empty.**

Two rules are enforced in code, not left to the prompt:

- **Sensitive questions** (work authorisation, sponsorship, salary, notice period, legal
  declarations, consent, demographic, disability and veteran questions) are filled only
  from Saved Answers the User entered. Otherwise they stay empty. Never a Suggestion.
- **Forms that ask for answers not written by AI** (detected from instructions such as
  "do not use AI" or "not AI-generated", and settable by the User per page) get Fact
  notes only. The extension does not generate prose for them, and does not rewrite AI text
  to look human-written: the User writes those answers, with their own Facts at hand.

Edited answers can be saved as Saved Answers so the next form reuses them.

### Writing Style

Suggestions should read like the User, not like generic AI text. JobWeaver builds a
**Writing Style** profile from text the User wrote themselves: the uploaded summary and
cover letters, Saved Answers they edited, and the final text of Suggestions they reworked
before saving. The profile records observable traits only (typical sentence length,
formality, first-person phrasing, words and openers the User uses or avoids, British or
American spelling) plus up to three short excerpts as examples. Excerpts come from text
that can hold claims (employers, achievements, numbers, outdated roles), so they are
redacted before storage: Company, product and person names, numbers, dates and
technologies are replaced with placeholders such as `[COMPANY]` or `[NUMBER]`, and an
excerpt that is still mostly claims after redaction is dropped. The prompt treats
excerpts as tone examples only. Redaction is not relied on alone: every Suggestion is
checked independently against the User's current Facts by the existing tailoring checks
(`backend/app/tailoring/checks.py`: technologies not in the Fact Bank, numbers without
evidence), and a failing Suggestion is regenerated once, then dropped to Fact notes
(ADR-0005).

- Built by a typed AI Gateway task, in recorded mode in CI, after the AI notice and region
  checks; rebuilt when its inputs change, and shown in Settings where the User can edit or
  clear it.
- Passed to the question-answering task alongside the Facts. Every Suggestion also avoids
  stock phrasing ("I am excited to", "leverage", "passionate about", "in today's
  fast-paced") through a code check that asks for one rewrite when it finds them.
- A User's Writing Style is User-owned data, scoped by `user_id` (ADR-0001), and is never
  used for another User.

## Existing building blocks and gaps

| Existing code | Reuse or required change |
| --- | --- |
| `backend/app/api/drafts.py` | Reuse versioned PDF and explicit Applied behavior through the existing services; retain ownership, warning and expected-version checks. |
| `backend/app/api/deps.py` | Current authentication resolves a session cookie. It does not yet support extension credentials. |
| `backend/app/services/auth.py` | Reuse the Google-authenticated User identity; add a narrowly scoped extension authorisation flow. |
| `backend/app/services/accounts.py` | `ensure_ai_allowed` gates every question-answering call. |
| `backend/app/tailoring/contact.py` | `contact_facts()` already extracts phone and profile links; reuse it to suggest profile values. |
| `backend/app/adapters/ats_urls.py` | Recognises Greenhouse, Lever and Ashby apply URLs; reuse it to pick a form adapter and to match a page to a Job. |
| `backend/app/models/user.py` | Name and email exist, but this is not a structured application profile. |
| Fact Bank and Draft snapshots | Preserve reviewed Facts, saved edits and Tailoring Trace; do not parse display text into assumed employment history. |

## Data to prepare

Add a User-owned application profile, editable in Settings: contact details, location,
professional links and structured employment/education entries. Fact Bank information may
be offered as a prefill suggestion, but the User must review it before it becomes an
autofill value. Store Fact references for imported claims; a removed or changed Fact must
make dependent values require review. Never derive years of experience or seniority from
a job description.

Saved Answers hold User-entered answers keyed by a normalised question plus the context
it applies to, so an answer is never reused where it would be wrong:

- **Scope:** `general` (notice period, relocation), `country` (work authorisation,
  sponsorship, salary, which also stores currency and period) or `company` (for example
  "Why this company?").
- **Applicability:** the country, currency and Company the answer was given for.
- **Provenance:** User-entered, or a Suggestion the User edited, with the Job and date.

Matching uses scope: a `general` answer is offered anywhere; a `country` answer only for a
Job in the same country, and salary only in the same currency and period; a `company`
answer is never filled for another Company and is at most shown as a starting point to
rework. Missing values remain unanswered.

Captured Jobs (ADR-0017) are stored as Postings from a push-only `captured` Source and
linked to the capturing User (ADR-0002). They contain only the public advert, never User
data. The link must be durable: today a Feed rebuild deletes links that no longer match
Preferences unless a Draft or Application exists (`backend/app/services/feed.py:431-435`),
so a captured Job outside Preferences would vanish before drafting. The User's link
records that it was captured (for example `captured_at` on `user_jobs`), the rebuild keeps
captured links like drafted ones, and a test proves a captured, nonmatching Job survives
rebuilds. Removing it is an explicit User action.

Proposed storage is a profile record with validated structured content and a version,
Saved Answers, and revocable extension authorisations. Final schema and retention rules
belong to the first implementation PR; all User-owned records and queries carry `user_id`
(ADR-0001).

## Extension and backend boundary

```text
User-approved JobWeaver connection -> extension service worker -> scoped backend API
Application page <-> on-demand content script <-> extension preview and fill controls
Scoped backend API -> existing ownership-checked Draft/Application services and AI Gateway
```

The service worker holds authorisation and talks only to a fixed JobWeaver origin.
Content scripts receive only the selected field values required for the current fill,
never the session cookie, extension credential, full Fact Bank or provider API keys.
Treat destination HTML and field labels as untrusted data. Validate message schemas,
sender tab/frame and current URL; no page-provided URL may become a privileged fetch.
Render labels as text, not HTML. Question text sent for answers is data, never
instructions to the AI. Invalidate a prepared fill when the page or form changes.

Use `activeTab`, `scripting` and extension session storage, with host access restricted
to the JobWeaver origin. `activeTab` gives temporary access to whichever site the User
clicked the extension on, so any site works without `<all_urls>`. Do not request cookies,
browsing history or `<all_urls>`. Cross-origin embedded forms (for example a Greenhouse
form inside a company careers page) need access to the frame's origin: request it as an
optional host permission, per host, at the moment it is needed, and show a manual fallback
if the User declines. Allowlisted field types, visible/enabled controls and recognised form
adapters determine what can be filled. Do not touch hidden inputs, passwords or arbitrary
page scripts.

## Authorisation proposal

Keep Google sign-in as the identity provider (ADR-0015). Connect through a JobWeaver web
page using the existing signed-in session and CSRF protection. The extension initiates a
short-lived challenge; the page shows the requested scopes and the User approves it.
Exchange an expiring, single-use code bound to the challenge and approved extension ID
for an opaque credential. Store only its hash server-side; support expiry and immediate
revocation from Settings. Never put credentials in page URLs or application-page storage.

The browser prototype must verify this handshake, sender-origin checks and unpacked
extension ID setup before profile endpoints ship. Keep credentials in extension session
storage accessible only to trusted extension contexts; after restart or expiry, reconnect
rather than adding a permanent refresh secret in the first release. Do not weaken existing
cookie/CSRF rules or enable wildcard CORS to make the extension work: the extension calls
the API from its service worker, which host permissions already allow (ADR-0008 unchanged).

Proposed scopes: read the reviewed profile and Saved Answers, list owned Draft metadata and
fetch a selected Draft/version, download its validated PDF, capture a Job, request answers
to form questions, save an answer, and explicitly mark an Application Applied. No Admin
access, Source controls, Gmail access or arbitrary API proxy. Typed extension API responses
expose the minimum data; regenerate frontend API types when endpoints are added. Credential
revocation and account deletion invalidate subsequent requests immediately.

## Form mapping and correctness

Implement a registry of form adapters under a new `extension/` directory, separate from
the backend Source registry. The generic adapter handles any page; Greenhouse, Lever and
Ashby adapters override it where they recognise the form. Each adapter enumerates fields
and fills permitted controls. Shared mapping uses labels, `autocomplete` metadata and known
field identities, rather than matching every input containing words such as name.

Use deterministic matching for profile fields and AI only for the form's own questions.
Test framework-controlled inputs (set the native value and dispatch input/change events),
dropdown values, repeated employment rows, file inputs, validation messages, multi-step
forms and rerendered forms. Ambiguous selectors or option meanings require manual entry.
Keep a per-fill in-memory record to offer Undo only where the current value still equals
what the extension wrote; never undo subsequent User changes. Rescanning must not overwrite
User edits.

## Delivery stages and acceptance

| Stage | Reviewable result and completion checks |
| --- | --- |
| 1. Policy and connection prototype | ADR-0017 and PRD/glossary changes reviewed; Chrome/Brave handshake demonstrated; credential expiry, replay, wrong-origin, revocation and cross-user tests pass. |
| 2. Reviewed profile, Saved Answers and Draft selection | Settings profile and Saved Answers editors; typed scoped APIs; Fact-change handling tested; exact saved Draft/PDF version shown. |
| 3. First working application | Generic adapter plus Greenhouse adapter; preview, selective fill, safe overwrite, Undo and PDF attachment with download fallback; fixture browser tests prove correct fields, attached file and no submit action. |
| 4. More forms and tracking | Lever and Ashby adapters, embedded-form host permissions, multi-step rescans; explicit Applied confirmation is idempotent; stale-version/expired-session errors preserve form input. |
| 5. Form questions and Writing Style | Gateway tasks in recorded mode for answers and for building the Writing Style; Saved Answer, Suggestion, Fact notes and Leave empty paths; Suggestions are complete answers within the field's length limit, use the Writing Style and pass the stock-phrase check and the Fact checks; Writing Style excerpts are redacted; the Writing Style editor in Settings; Saved Answers are reused only within their scope; sensitive questions never get a Suggestion and forms that refuse AI answers get Fact notes only, all proved by tests. |
| 6. Captured Jobs | Capture from JSON-LD and page text with User review; push-only `captured` Source; a durable captured link that survives Feed rebuilds when the Job does not match Preferences, proved by a test; the Job flows into the existing Draft. |
| 7. Private testing | Installable extension ZIP, reproducible build, permission review, supported-form matrix and manual trial on real forms without submitting test applications. |
| Later | Workday multi-step forms, Firefox, store publication. |

For each implementation stage, run relevant backend ownership/auth tests, frontend tests,
extension type/lint checks and browser tests. Fixtures must cover filled fields, existing
values, unknown/sensitive fields, malicious labels/messages, SPA transitions and disabled
controls. No live provider calls or real employer submissions in CI. Record supported
browser/site variants and known manual steps rather than claiming universal autofill.

## Rollout, cost and open decisions

Use a server feature flag and a private unpacked-extension pilot first. Disabling extension
authorisation must leave the existing Feed, Drafts and Applications usable. Filling profile
fields uses no AI credits and runs in the browser; form questions use the existing free AI
providers and their quotas. No new microservice is planned. Measure actual API latency and
resource use on the current VM before expanding scope. Do not log profile values, form
answers, question text, credentials, resumes or complete destination URLs with query
strings.

Review before implementation: exact profile fields and schema; authorisation lifetime and
connection UX; the sensitive-question list; how a form's instruction against AI answers is
detected. Public store publication, Firefox/Safari and Workday require their own follow-up
decisions. No changes to production are authorised by merging this plan.

## Browser references

- [Temporary access through activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
- [Optional host permissions requested at runtime](https://developer.chrome.com/docs/extensions/reference/api/permissions).
- [Extension messaging and trust boundaries](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).
- [Service-worker requests and host permissions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
