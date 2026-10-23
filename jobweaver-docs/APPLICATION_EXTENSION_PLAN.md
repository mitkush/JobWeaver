# Application form extension plan

Status: proposed, for review in a draft PR. This document adds no extension, endpoint,
permission, migration or deployment change. The stages below are implementation proposals,
not promises that a particular third-party form already works.

## Goal and first release

Help a User apply to a Job from their Feed by filling a form with reviewed information
and using a specific saved Draft version. The User reviews the destination form, attaches
files and submits it themselves, then explicitly marks the Application Applied.

Start with an unpacked Manifest V3 extension for Chrome and Brave on desktop. Support
Greenhouse and Lever application forms first, with tested adapters for their supported
hosts and form variants. A generic mapper can offer basic contact fields only when the
mapping is unambiguous. Unsupported fields stay visible as manual work.

Outside the first release: automatic submission or Next-button clicks, bulk applications,
LinkedIn Easy Apply, Workday, CAPTCHA handling, automatic file uploads, AI-generated custom
answers, scraping new Jobs and public extension-store distribution. Adding an application
form adapter is separate from adding a Source Adapter: it does not discover Postings.

## User flow

1. On a saved Draft, select a version and PDF layout, then open the application link.
   Unsaved edits must be saved before that version can be used.
2. Click the extension and connect JobWeaver if necessary. Select the intended Job and
   Draft; show Company, title, destination hostname, version number and save time.
   URL matching may suggest a Job, but cannot silently select an ambiguous match.
3. Scan the current form on demand. Preview each proposed field, its value and its source.
   Allow selection of individual fields. Existing nonempty fields are skipped by default;
   overwriting requires a separate explicit selection.
4. Click Fill selected fields. Report filled, skipped and failed fields separately.
   Preserve existing input on errors and rescan after a page transition when requested.
5. Download the selected Tailored Resume or Cover Letter using JobWeaver's existing PDF
   generation and validation. Attach files manually in the first release. Display the
   exact version and filename so a newer Draft cannot silently replace the selected PDF.
6. Review and submit on the employer's site. The extension never clicks Submit. A separate
   I submitted this application action updates the Application through JobWeaver.
   Filling fields or detecting a confirmation page alone does not mark it Applied.

## Existing building blocks and gaps

| Existing code | Reuse or required change |
| --- | --- |
| `backend/app/api/drafts.py` | Reuse versioned PDF and explicit Applied behavior through the existing services; retain ownership, warning and expected-version checks. |
| `backend/app/api/deps.py` | Current authentication resolves a session cookie. It does not yet support extension credentials. |
| `backend/app/services/auth.py` | Reuse the Google-authenticated User identity; add a narrowly scoped extension authorisation flow. |
| `backend/app/models/user.py` | Name and email exist, but this is not a structured application profile. |
| Fact Bank and Draft snapshots | Preserve reviewed Facts, saved edits and Tailoring Trace; do not parse display text into assumed employment history. |

## Data to prepare

Add a User-owned application profile, editable in Settings: contact details, location,
professional links and structured employment/education entries. Fact Bank information may
be offered as a prefill suggestion, but the User must review it before it becomes an
autofill value. Store Fact references for imported claims; a removed or changed Fact must
make dependent values require review. Never derive years of experience or seniority from
a job description.

An optional saved-answer section can hold User-entered notice period, salary expectations
with currency/period, relocation and work-authorisation answers. Missing values remain
unanswered. Protected demographic, disability, veteran, consent and legal declaration
fields remain manual in the first release, even if their labels look familiar.

Proposed storage is a profile record with validated structured content and a version, plus
revocable extension authorisations. Final schema and retention rules belong to the first
implementation PR; all User-owned records and queries carry `user_id` (ADR-0001).

## Extension and backend boundary

```text
User-approved JobWeaver connection -> extension service worker -> scoped backend API
Application page <-> on-demand content script <-> extension preview and fill controls
Scoped backend API -> existing ownership-checked Draft/Application services
```

The service worker holds authorisation and talks only to a fixed JobWeaver origin.
Content scripts receive only the selected field values required for the current fill,
never the session cookie, extension credential, full Fact Bank or provider API keys.
Treat destination HTML and field labels as untrusted data. Validate message schemas,
sender tab/frame and current URL; no page-provided URL may become a privileged fetch.
Render labels as text, not HTML. Invalidate a prepared fill when the page or form changes.

Use `activeTab`, `scripting` and extension session storage, with host access restricted
to the JobWeaver origin. Do not request cookies, browsing history or `<all_urls>`.
Start with top-level and same-origin form content. Cross-origin embedded forms need a
separate explicit host-permission design; show a manual fallback until supported.
Allowlisted field types, visible/enabled controls and recognised form adapters determine
what can be filled. Do not touch hidden inputs, passwords or arbitrary page scripts.

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
cookie/CSRF rules or enable wildcard CORS to make the extension work.

Proposed scopes: read the reviewed profile, list owned Draft metadata and fetch a selected
Draft/version, download its validated PDF, and explicitly mark its Application Applied.
No Admin access, Source controls, Gmail access or arbitrary API proxy. Typed extension API
responses expose the minimum data; regenerate frontend API types when endpoints are added.
Credential revocation and account deletion invalidate subsequent requests immediately.

## Form mapping and correctness

Implement a registry of form adapters under a new extension directory, separate from the
backend Source registry. Each adapter detects a supported page, enumerates fields and
fills permitted controls. Shared mapping uses labels, autocomplete metadata and known
field identities, rather than matching every input containing words such as name.

Use deterministic matching for first-release fields. Test framework-controlled inputs,
dropdown values, repeated employment rows, validation messages and rerendered forms.
Ambiguous selectors or option meanings require manual entry. Keep a per-fill in-memory
record to offer Undo only where the current value still equals what the extension wrote;
never undo subsequent User changes. Rescanning must not overwrite User edits.

## Later AI answers and architecture decisions

Custom-question suggestions are a later stage. They must use typed tasks in the existing
AI Gateway, recorded test mode, usage accounting, quotas, fallback and current AI notice
and region checks (ADR-0007). Generate only from the User's reviewed Facts, with a Tailoring
Trace and explicit review before insertion (ADR-0005). Send only necessary question text
and Facts; do not send full page HTML or follow instructions embedded in the page.
Use background work if generation can exceed a short request deadline.

ADR-0006 currently describes the outward action as Gmail Hand-off. Before shipping form
filling, propose an explicit ADR amendment and corresponding PRD/glossary changes covering
User-initiated disclosure of selected values to application sites while retaining human
submission. Filling may trigger an employer site's autosave before Submit, so the preview
must explain that pressing Fill shares those selected values with that site. This plan
does not silently change the existing decision. No new AI provider is needed.

## Delivery stages and acceptance

| Stage | Reviewable result and completion checks |
| --- | --- |
| 1. Connection prototype and policy | ADR/PRD changes reviewed; Chrome/Brave handshake demonstrated; credential expiry, replay, wrong-origin, revocation and cross-user tests pass. |
| 2. Reviewed profile and Draft selection | Settings profile editor and typed scoped APIs; validation and Fact-change handling tested; exact saved Draft/PDF version shown; no application-site access needed yet. |
| 3. First working application | Greenhouse adapter, preview, selective fill, safe overwrite and Undo; manual attachment and submission; fixture browser tests prove correct fields and no submit action. |
| 4. Second adapter and tracking | Lever adapter and explicit Applied confirmation; duplicate confirmation is idempotent; stale-version/expired-session errors preserve form input. |
| 5. Private testing | Installable extension ZIP, reproducible build, permission review, supported-form matrix and manual trial on real forms without submitting test applications. |
| Later | Generic mapping improvements, further ATS adapters, supported upload automation and separately reviewed AI question suggestions. |

For each implementation stage, run relevant backend ownership/auth tests, frontend tests,
extension type/lint checks and browser tests. Fixtures must cover filled fields, existing
values, unknown/sensitive fields, malicious labels/messages, SPA transitions and disabled
controls. No live provider calls or real employer submissions in CI. Record supported
browser/site variants and known manual steps rather than claiming universal autofill.

## Rollout, cost and open decisions

Use a server feature flag and a private unpacked-extension pilot first. Disabling extension
authorisation must leave the existing Feed, Drafts and Applications usable. Ordinary filling
uses no AI credits and runs in the browser; no new microservice is planned. Measure actual
API latency and resource use on the current VM before expanding scope. Do not log profile
values, form answers, credentials, resumes or complete destination URLs with query strings.

Review before implementation: exact profile fields and schema; authorisation lifetime and
connection UX; initial Greenhouse/Lever form variants; whether optional saved answers belong
in the first release. Public store publication, Firefox/Safari and automatic uploads require
their own follow-up decisions. No changes to production are authorised by merging this plan.

## Browser references

- [Temporary access through activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
- [Extension messaging and trust boundaries](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).
- [Service-worker requests and host permissions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
