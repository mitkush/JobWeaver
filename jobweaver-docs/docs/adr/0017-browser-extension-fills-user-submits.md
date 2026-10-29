# A browser extension fills application forms; the User submits

For Jobs without a contact email, applying means filling an employer's form by hand. A Chrome extension (FR-E14) fills it instead: on any site the User clicks it on, it fills profile fields from a reviewed application profile, attaches the selected Draft version's Tailored Resume and Cover Letter, and suggests answers to the form's own questions. The User reviews the page and submits it; the extension never submits, never clicks Next and never applies in bulk. Marking the Application Applied stays a separate, explicit User action. This extends ADR-0006 from Gmail to application forms: JobWeaver still sends nothing on its own, but pressing Fill shares the selected values with that site, which may autosave them before Submit, and the preview says so.

The extension calls only a scoped `/api/ext/` surface, from its service worker, with an opaque credential issued through a challenge the User approves on a signed-in JobWeaver page; only its hash is stored, it expires and can be revoked. Cookie and CSRF rules and the no-CORS setup (ADR-0008) are unchanged. Access to the employer's page comes from `activeTab` on the User's click, never `<all_urls>`.

Questions on a form are sent as question text only and answered through a typed AI Gateway task after the AI notice and region checks: a Saved Answer, a Suggestion written only from the User's Facts with a Tailoring Trace (ADR-0005), Fact notes, or nothing. A Suggestion is a complete answer sized to the field and its stated limit, written in the User's **Writing Style**: observable traits and short excerpts taken from text the User wrote themselves, with names, numbers, dates and technologies redacted. Each Suggestion is still checked against current Facts by code, so the style cannot add claims. The User reworks it before use. Saved Answers carry their scope (general, country or Company), applicability and provenance, and are reused only within that scope. Code enforces two rules: sensitive questions (work authorisation, sponsorship, salary, notice period, legal declarations, consent, demographic, disability, veteran) are filled only from Saved Answers the User entered; and a form that asks for answers not written by AI gets Fact notes only, never generated prose and never AI text rewritten to look human-written.

A job page JobWeaver has not fetched can be saved as a **Captured Job**: the extension reads the public advert, the User reviews it, and it is stored as a Posting from a push-only `captured` Source, linked to that User (ADR-0002) by a durable captured link that Feed rebuilds keep even when the Job does not match Preferences. It contains no User data.

When a careers page shows a fuller description than the stored one, the User can keep it as a **Page Description** on their own link to the Job, not on the shared Job, because it comes from one User's browser and is unverified. It is always offered, whatever its length. Drafts use it when present; an existing Draft gets it only through a new version, and each Draft version keeps its own immutable job context (description, its origin and the required skills taken from it), so regenerating never changes how an older version is checked or exported. The Job chosen on an advert page stays with that tab and the tabs it opens, so a two-step application (advert, then form) keeps its Job, with one confirmation before filling.

**Considered and rejected:** submitting forms or clicking through steps automatically (the PRD's auto-apply non-goal, and a mis-filled submission cannot be withdrawn); `<all_urls>` host access (the extension would read every page the User visits); session cookies with a CORS allowlist (weakens the single-origin model); "humanising" AI answers for forms that forbid AI (misrepresents the answer to the employer); AI guesses for sensitive questions (a wrong work-authorisation or salary answer is costly and the AI has no way to know it).

**Consequences:** a new credential type and the `/api/ext/` surface need ownership, expiry, replay and revocation tests (ADR-0001); the push-only `captured` Source is the first Source that does not fetch, so its adapter's fetch does nothing and core code still never branches on its name (ADR-0003); employer pages and question text are untrusted input; Saved Answers and the application profile are new User-owned data; extension-store publication is part of the public launch gate (ADR-0012).

## Increment: reviewed letter reuse and local copies

The combined background-and-interest question may reuse the selected Draft version's existing Cover Letter body, without a new AI call or sending question text to a provider. The proposal is editable, starts unticked, and requires the User to review and tick it before filling. Other questions were manual until the typed question-answer task was built (see the next increment). Fields too short for the letter stay manual, and detected no-AI instructions suppress this prose proposal. Detection is conservative, not a guarantee; the User must check the form's instructions.

Attachment names are `Name_Resume.pdf` and `Name_Cover_Letter.pdf`. An explicit Save PDFs in company folder action requests optional browser Downloads access and saves copies under Downloads/<company>/. It does not create local files just by scanning or filling. The browser's download settings may still ask where to save.

## Increment: one active package, side panel and reviewed answers (Oct 2026)

Implemented together, following `APPLICATION_UX_PLAN.md`. This supersedes the earlier user-visible multiple Draft packages and separate captured-page packages.

- **One active Draft per User and Job.** A database index enforces it. Generating again, or a Page Description saved for a Job that already has a Draft, prepares a **Replacement**: background AI work, based on one version, for the resume, the cover letter or one resume section. The accepted document does not change until the User accepts it; acceptance is refused when the Draft or a cited Fact changed meanwhile, and Undo restores the previous version. Archiving replaces deletion and keeps versions and Application history. Edits autosave as versions; versions are never merged, because the extension pins version numbers.
- **Side panel.** The toolbar button opens the panel, which grants `activeTab` for that tab; other sites are reached only through an optional per-site host permission the User grants in the panel. Forms embedded from another site are found with the optional `webNavigation` permission and scanned, filled and undone per frame once their site is allowed. Unfinished review is kept in session storage for 30 minutes, scoped to the connection, page, Draft and version. A fill prepared before the document changed is refused.
- **Mark as applied** in the panel requires the User to confirm they submitted the form, is idempotent, and records the attached version on the Application.
- **Reviewed answers.** The typed `answer_questions` task is built: only question labels and the Job are sent, at most 12 per request, after the AI notice and region checks. Each Suggestion is checked by the same code as a cover letter line (ADR-0005) and becomes Fact notes when it fails or cites nothing; stock phrasing is flagged. Suggestions appear unticked in an editable box, and only the text the User reviewed is filled. A sensitive question gets a Saved Answer or nothing from JobWeaver; the User may still type their own answer in the panel, as they could on the page. Reviewed answers can be saved from the form with a scope. Writing Style is built by the `describe_writing_style` task from the User's summary and saved non-sensitive answers; code redacts its excerpts again on every save, including the User's own edits.
- **Access list version 4:** reconnecting asks the User to approve Mark as applied and answer suggestions.
- **Store build:** `npm run build:store` leaves out the pinned key, so the Chrome Web Store assigns its own ID, which must be added to `EXTENSION_IDS` beside the unpacked one. The privacy policy is served at `/privacy/extension`.

### Answer context and provenance

Form-answer requests from the extension include its selected Draft and exact saved number.
When AI needs job context, the server verifies ownership and Job membership and uses that
version's immutable context, including for an archived package. Saved-only requests and
no-AI Fact notes do not need a Draft pin. Legacy clients without a pin use current context.
No-AI instructions also suppress Saved Answers originating as AI suggestions; saving or
reopening a suggestion does not turn it into a user-authored answer. User-entered Saved
Answers remain available, including sensitive answers. No-AI filtering happens before scope
ranking, so an excluded suggestion cannot hide an eligible manual answer. Unvalidatable provider output
becomes Fact notes rather than an HTTP error. Generated answers are requested within the
2,000-character validation limit. Responses are fitted at a sentence boundary within that
limit and the field limit, then Fact-checked. An oversized response with no fitting sentence
receives a specific length warning.
