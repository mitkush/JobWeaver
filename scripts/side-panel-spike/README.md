# Side-panel permission spike

This independent unpacked extension reads only synthetic local fixture titles and URLs.
It has no JobWeaver credentials, account connection, employer fields or submission code.
It is not included in the production extension build.

## Reproduce automated checks

Install Playwright in a separate scratch directory and its Chromium browser, then:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright/index.mjs node scripts/side-panel-spike/run.mjs
```

The runner opens Chrome for Testing from Playwright and the installed macOS Brave binary
in separate temporary profiles. It runs local HTTP fixtures, opens a real side panel using
an extension-page button, clicks Apply to a new tab on another local origin, and records
scan failures/successes before/after optional origin grants. It checks a cross-origin
navigation back to the first granted site. Browser profiles are removed on exit.

`--auto-confirm-dialogs-for-testing=accept` simulates accepting permission dialogs only in
these isolated profiles. CDP evaluations run with a user gesture in the actual panel target.
This verifies permission enforcement and panel availability, not normal dialog usability
or toolbar-derived activeTab activation. Do not enable this flag in a personal browser.

A repeat run timed out during optional-permission approval in both browsers. The runner
returns a nonzero exit code for this condition; normal permission-dialog verification is
still required. See the results and limitations in
[jobweaver-docs/SIDE_PANEL_PERMISSION_SPIKE.md](../../jobweaver-docs/SIDE_PANEL_PERMISSION_SPIKE.md).

## Remaining manual checks

1. Load this directory unpacked through the browser's extensions page in a test profile.
2. Open a synthetic local advert, then click the extension toolbar icon or configured
   Command+Shift+Y shortcut. Confirm Scan works through activeTab.
3. Follow Apply into a new tab and confirm the existing panel does not grant that tab access.
4. Try a cross-origin same-tab navigation with only activeTab and verify revocation.
5. Grant optional access to the local site through its normal browser dialog; test denial,
   acceptance and revocation. Check that the UI explains the next action each time.
6. Repeat in installed stable Chrome and Brave. Record full versions.

The panel's Allow current fixture site button requires the tab URL to be readable. Without
activeTab or an existing host grant, tabs.query does not expose that URL. Future UX cannot
silently calculate every new tab's permission origin: use a known Apply destination or ask
for a toolbar activation when the destination is unknown. This spike does not request tabs
permission or access to all employer sites.
