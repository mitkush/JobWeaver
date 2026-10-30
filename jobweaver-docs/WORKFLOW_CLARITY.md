# Application workflow clarity

This follow-up builds on APPLICATION_UX_PLAN.md and VISUAL_POLISH.md. It does not replace the document lifecycle, selected-version rules or Fact Bank checks.

## Changes

- Feed: skill comparisons show the first four matched and missing skills separately, with labelled disclosures for each remainder. Correspondence with more than two Sources collapses behind a disclosure. All items remain accessible. Card alignment, Saved, Viewed and remembered filters are unchanged.
- Job: one application action panel contains status, Create/Open draft, Save, Hide and the original advert link. It sits beside the JD on desktop and scrolls normally, so long sidebars remain reachable. On phones the action panel comes first, then the JD, then the skills comparison. Existing safe JD formatting and provenance remain.
- Draft preparation: show actual server progress and a clock labelled "Waiting here". The clock measures time on this screen, not total server execution time or an estimated completion time. Leaving does not cancel generation. Known uniform gateway failures get fixed recovery guidance for timeouts, usage/rate limits, oversized requests or missing configuration. Mixed failures remain explicitly uncertain. Provider diagnostic bodies remain in logs.
- Resume review: a collapsed evidence inventory and review checklist encourages relevant work examples, supported outcomes and readable PDF layout. Counts are not scores or proof of quality. It neither changes generated content nor pads the resume with projects. Existing warnings and Tailoring Trace remain authoritative.
- Extension: show the current next step, distinguish reading a JD from scanning fields, update guidance after capture/scan/fill, and explain recovery when no supported fields are found. Permission, confirmation, attachment pinning and never-submit behavior are unchanged.
- CI: cancel superseded PR runs and scope PR checks by changed paths. Backend changes also run frontend generated-type checks and Docker. Unknown paths and workflow changes run everything. Every push to main runs all checks. Deployment now requires that exact main push run; parent-run fallback is removed because PR runs can be scoped. No billing setting is changed.

## Validation

Local tests cover disclosure accessibility, elapsed-time continuity across provider progress, extension empty-form guidance, safe gateway recovery messages and CI scope selection. Brave production-preview walkthrough uses synthetic data, never live employer submissions: Feed disclosures, exactly one Job Draft action, phone/desktop layout, both themes, generation progress and the resume checklist.

CI still needs to run once GitHub Actions allowance is available. Local checks do not substitute for the exact-main deployment gate. No migration or API shape change is needed. Deploy the server after merge; rebuild/reload the unpacked extension for the guidance changes. No new extension permission or reconnect is required.

Local validation on 30 October 2026: 945 backend tests, 148 frontend tests, 98 extension tests and 6 CI scope tests passed. Backend format/lint, frontend lint/typecheck/build and extension typecheck/build passed. Brave walkthrough passed at 1440px and 375px, including light/dark mobile Job views, without horizontal overflow or JavaScript errors. Real employer forms and the native site-permission prompt were not retested for these text-only extension changes. Docker image builds were not run locally; that check remains required on main before Actions deployment.
