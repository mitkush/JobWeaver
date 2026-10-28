# JobWeaver application workflow improvement plan

Status: approved 28 October 2026. Stages 1 to 8 are implemented in one PR; the Chrome Web Store submission itself is a separate release action (`EXTENSION_STORE_LISTING.md`). Earlier packages of a Job are archived by migration 0017, never deleted, and listed on the Job page.

## Agreed outcome

One understandable journey across Job detail, Draft and extension: understand job -> prepare documents -> review -> scan application -> review fields -> fill -> inspect and submit yourself.

One active Draft package per user and Job. Resume and cover letter regenerate independently. Existing packages need a deterministic migration policy: retain historical records, expose the current package, and never delete application-linked documents merely to simplify the UI. Determine selection from current application/Draft references and timestamps; explicitly surface ambiguous legacy packages during migration rather than silently choosing and deleting.

## Screen behavior

Job detail:
- Put a readable full JD first, with headings, paragraphs and bullets preserved when available. Keep plain text safe and format conservatively; do not invent requirements or rewrite the JD with AI for presentation.
- Show title, company, location/work mode, posted date, available experience hint and application status.
- Attribute the description to its actual provider or the user's captured careers page, including source URL and capture time where available.
- Primary action opens the current Draft or creates one. Open original advert is secondary. Collapse Sources/Correspondence and duplicate tools below the JD; explain globally affecting split/merge actions before executing them.
- Preserve Feed search/filter context on return. Make actions usable at narrow widths.

Draft workspace:
- Start with a readable resume preview. Selecting a section opens direct editing and section-scoped AI instructions. Cover letter has its own document view and actions.
- Autosave direct edits after a short pause. Show Saving / Saved / Couldn't save. Keep unsaved text on failures and guard navigation. Prevent stale responses from overwriting newer edits; use server revision checks and explicit conflict recovery.
- Keep Preview accessible. Wait for pending edits to save before generating the preview, and explain save failures beside the action.
- Regenerate resume and Regenerate cover letter are secondary actions. The current accepted document stays usable while generation runs or fails.
- AI output is a proposed replacement, including section-level AI edits. Show Use this replacement / Keep current. Accept atomically against the document state used to generate it; manual edits made meanwhile must trigger conflict review, never be overwritten silently.
- Offer Undo after acceptance. Store the preceding accepted content internally. Hide version numbers and version selectors from normal workflow. Preserve fixed document/job-context snapshots needed for historical applications, prior attachments and trace checks.
- Fact warnings remain visible as a concise summary linked to affected content. Citations, Base Resume and comparisons are expandable. Apply no-fabrication checks to candidates before acceptance.
- Independent regeneration preserves the other document and its manual edits. Application email behavior stays scoped explicitly; it is not silently regenerated alongside another document.

Extension side panel:
- Replace long popup tasks with a persistent side panel. Show company/title throughout and one primary next action for the current state.
- States: disconnected; read job; review captured JD; saved job; preparing documents; generation failed; ready for review; selected document; scan; review proposals; fill report.
- Restore unfinished captured-JD edits and edited background answers after closing/reopening. Scope state by user, tab and page/job identity; clear or reconfirm on identity changes, expiry and disconnect. Treat credentials separately from editable review state.
- Carry job context across same-tab and new-tab Apply navigation. Ask Continue with this job / Choose another job when the destination is uncertain. Do not silently attach an unrelated resume.
- Preserve the explicit selected document identity internally, while presenting simple current/updated status. After an accepted replacement, invalidate prepared fills and require a fresh scan/review. Already attached files remain until the user explicitly replaces them.
- Review proposed values before filling. Mark replacements; existing values and generated background answers start unticked. Fill only selected fields, retain Undo, and never submit.
- Consolidate repeated Open Draft / Use Draft controls into one job/document panel. Put manual unrelated-Draft selection behind Choose another job/document.
- Distinguish absent data from expired connection and temporary service errors. Preserve selections on transient failures. Validate service-worker reply shapes, restore busy controls after failure, and show actionable Retry.
- Explain no-form and unsupported embedded-form states. Side-panel changes alone do not add cross-origin iframe support.
- Downloads report the destination and success/failure. Fill report distinguishes Filled / Needs attention / Nothing filled.

## Delivery stages

1. Reliability PR + browser permission spike: run the Chrome/Brave same-tab, cross-origin and new-tab Apply permission spike alongside navigation protection; recoverable typed extension errors; keep selection on transient failures; explicit job-context confirmation; regression coverage for data loss and wrong-document paths.
2. Document lifecycle PR: one active package; independent candidate generation/acceptance; background AI candidate jobs; autosave conflicts; immutable per-version job context, Fact/content snapshots and Undo; migration of legacy packages; API type regeneration. Update PRD and ADR-0017 where present behavior changes.
3. Job-page PR: safe readable JD rendering, actual provenance, content ordering, consolidated actions and return context. Preserve new ingestion structure where needed; avoid a costly blanket refetch of historical descriptions.
4. Draft workspace PR: preview-first section editor, autosave status, candidate review, grouped warnings and secondary menus.
5. Extension side-panel PR + Mark as applied: explicit user-confirmed, idempotent Applied tracking; persistent state-driven workflow, context carryover, proposal review, document-update invalidation, restored unfinished edits and consolidated controls. Verify supported Chromium/Brave behavior and required permissions before rollout.
5b. Embedded forms: optional frame-origin permissions, frame-scoped scan/fill/Undo, multi-step rescans and real Greenhouse/Lever browser checks. Explain unsupported frames until this slice is ready.
6. Integration/polish PR: responsive layouts, keyboard/focus handling, accessible statuses, browser walkthroughs and recovery scenarios.

7. General AI answers and Writing Style: after background candidate jobs and the panel stabilize, add reviewed gateway-generated suggestions, scoped Saved Answers and sensitive-question restrictions. Preserve existing cover-letter-derived background answers throughout.
8. Web Store distribution: after browser acceptance, prepare packaging, permission/privacy disclosures and store review. Personal unpacked installation remains available before this milestone.

Each PR should be independently reviewable and tested. Keep intermediate server/client compatibility, feature-gate incomplete lifecycle transitions, and do not expose the redesigned controls before their underlying behavior is ready.

## Acceptance walkthroughs

- Existing Feed Job and a directly visited careers-page Job absent from JobWeaver both complete the journey.
- Read JD -> edit/reopen review -> save -> create Draft -> edit a section -> autosave -> preview -> open employer application -> confirm job -> scan -> review background answer -> close/reopen panel -> fill -> inspect -> Undo.
- Generate resume only: cover letter is unchanged. Reject candidate: current resume remains. Accept: selected current resume changes, prepared extension fill is invalidated, and Undo restores preceding accepted content.
- Failed generation, expired connection, unavailable server, deleted Draft, concurrent edits, out-of-order saves and navigation during save retain recoverable work and show useful actions.
- Historical application document snapshots and their job context remain stable after later regeneration.
- Same-tab/new-tab Apply carryover works; unrelated-job navigation requires confirmation. Previously attached files are not silently replaced.
- Test generic and Greenhouse forms in a browser without submitting, including existing values/files and Undo after panel closure. Clearly report Workday/iframe or other unsupported behavior rather than implying universal support.
- Verify narrow layout, both themes, keyboard navigation, focus restoration and screen-reader announcements.

## Implementation discovery checkpoints

Inspect existing DraftVersion/Application references and PDF generation before choosing the lifecycle schema. Verify side-panel API behavior in supported browsers. Define review-state persistence limits and cleanup. Measure preview/autosave performance on the existing small VM. These are engineering investigations, not additional product choices; report any constraint that would materially alter the agreed experience.

## Verified review amendments

Verified against main 0a56a3b. These amendments take precedence over ambiguous wording above.

- Add an early browser feasibility spike alongside reliability work, before committing to detailed side-panel design. Test Chrome and the installed Brave version, same-tab cross-origin navigation, new-tab Apply, toolbar activation, scan from the panel, and optional per-site host grants. An open panel does not itself give access to another tab. Record the permission interaction required and retain the popup fallback if the target browser fails. Time-box the investigation; do not promise a one-day implementation outcome.
- Explicitly supersede #64's user-visible multiple Draft packages and #58's separate captured-page packages with one active package. Preserve legacy application links and historical documents. Update FR-E8, FR-E11, ADR-0006 where its Save wording changes, ADR-0017 and APPLICATION_EXTENSION_PLAN.md with the lifecycle PR. Saving continues to have no Gmail/employer side effect; autosave does not reverse that safety rule.
- Reuse DraftVersion for accepted immutable content/Fact snapshots and Undo. Contrary to the review claim, current DraftVersion has no immutable job context: description/required skills/origin live on Draft.job_snapshot. Add and backfill per-version job context, and update all checks/exports to use it before accepting replacements based on another JD. Do not mutate a version already referenced by an attachment or application merely to coalesce autosaves. Define debouncing and internal checkpoint/retention policy during schema design; no need for a second parallel snapshot model.
- Add background candidate jobs explicitly in the lifecycle PR, before section AI UI. Current chat is synchronous with a 90-second timeout and 20-second routes; do not merely raise that HTTP timeout or assume the personal Claude route applies. Add scoped authorization/consent, queue/recovery, progress, cancellation/stale-result handling and atomic acceptance; choose task routing and budgets deliberately.
- Add explicit Mark as applied to the side-panel stage, with user confirmation and idempotent application tracking. Filling or downloading never marks Applied automatically.
- Add embedded-form support as an explicit follow-up slice after panel/permissions and before general-distribution readiness: optional frame-origin permission, frame-scoped scan/fill/Undo, multi-step rescans, and Greenhouse/Lever browser tests. Until then explain unsupported embedded forms and offer opening the hosted form where available.
- General AI question suggestions and Writing Style remain a separate follow-up after lifecycle/background jobs and panel stabilization. Existing reviewed cover-letter-derived background answers remain supported throughout. Web Store packaging/review is a later distribution milestone after permission/privacy disclosures and browser acceptance; it is not required to use the unpacked extension personally. Six stages describe reviewable scopes, not a guaranteed six-PR count or duration.
- Existing plain-text descriptions can still gain paragraph spacing, line width and conservative list rendering. Original heading semantics removed at ingestion cannot be recovered reliably without original data. Avoid promising that readability improves only for new jobs.
- Pinned document acceptance test: accepting a replacement mid-application never silently changes the attachment or PDF pinned for that application. Mark it Updated, invalidate prepared filling, and require explicit selection of the replacement plus a fresh scan/review. Old pinned content/job context remains stable until that choice. This clarifies the earlier selected-current wording.
