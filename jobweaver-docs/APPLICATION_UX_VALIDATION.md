# Application UX review validation

PR #68 follow-up, 28 October 2026.

## Corrections

- Invalid or unsupported AI answers become Fact notes instead of breaking the request.
- Answer generation uses the exact selected Draft version's job context and checks ownership.
- Saved AI suggestions retain their origin after editing, saving and reopening. Forms refusing AI do not reuse them.
- Saving an answer acknowledges success. Editing it updates the same scoped answer; choosing another scope creates a separate answer.
- Draft document tabs clear section selection and support arrow-key navigation.
- Form field labels, values and sources have separate lines. Scan becomes a secondary action after review starts, and an already recorded application cannot be marked Applied again.

## Browser walkthrough

Passed in Brave 155 using synthetic data, an isolated local database, recorded AI responses and a fixture careers site. The recorded answer reference was mapped to the scanned field so the supported suggestion path could be exercised through the real validation service.

Covered connection approval, job capture, Draft generation and selection, field scanning, unticked suggestions, sensitive questions left empty, scoped answer save and update, PDF attachment, reopening and Undo, explicit Applied confirmation, replacement acceptance and Undo, archived Draft discovery, Writing Style redaction and the public privacy page. The fixture form was submitted zero times.

Draft and Job pages had no horizontal overflow at 320px. Draft light and dark themes, document-tab keyboard navigation and the extension's field hierarchy were checked.

## Limits

The walkthrough opened the extension's fallback window. It did not verify the native side-panel toolbar interaction, the browser's optional site-permission dialog, or real Greenhouse, Lever or Workday forms. Those still need a manual check before release. No production data or live AI provider was used.
