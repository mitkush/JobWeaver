# Side-panel permission spike, 28 October 2026

## Result

A persistent side panel is feasible in the tested Chrome for Testing and Brave builds,
but it does not grant page access merely by being open. The application flow must account
for per-site authorization before scanning an unapproved destination.

| Scenario | Chrome for Testing 156.0.8078.4 | Brave 155.0.8059.80 |
| --- | --- | --- |
| Open actual panel from an extension-page user action | Passed | Passed |
| Scan fixture without page permission | Refused as expected | Refused as expected |
| Accept optional first-origin grant, then scan | Passed | Passed |
| Apply opens another origin in a new tab; scan without that origin grant | Refused as expected | Refused as expected |
| Accept second-origin grant, then scan new tab | Passed | Passed |
| Same-tab cross-origin navigation back to first granted origin | Passed | Passed |

The table records the initial successful run. A repeat using the committed runner opened
the panel and confirmed denial before access in both browsers, but then timed out waiting
for the optional-permission request to resolve. Permission-dialog automation is not yet
repeatable; do not treat the full matrix as a stable automated acceptance suite.

Two fixture origins were used: 127.0.0.1 and localhost, with an ephemeral local port.
No production account, real resume or employer form was used.

## Boundaries of the evidence

The runner used a real panel target but simulated user gestures and permission-dialog
acceptance in disposable profiles. This is not a completed manual employer-application
walkthrough. The installed stable Chrome did not load the command-line unpacked extension:
its worker never appeared. That is a test-install limitation, not evidence that Chrome's
side-panel API is unsupported. Chrome for Testing was used for the successful Chrome run.

macOS refused automated toolbar shortcut keystrokes with error 1002 (osascript is not
allowed to send keystrokes). Normal toolbar activation, normal permission-dialog clicks,
activeTab revocation during same-tab cross-origin navigation, and installed stable Chrome
manual loading remain unverified. The successful cross-origin test used explicit host
grants and must not be interpreted as activeTab persisting across origins.

## Stage 5 design consequence

Prefer optional per-site grants on explicit user action, with a toolbar-click fallback
when access or the destination origin is unknown. Carrying a Job to another tab is distinct
from being authorized to read/fill that tab. Without page access, tabs.query may omit the
new tab's URL; do not design Allow this site around information the extension cannot read.
A known Apply destination can supply an origin; otherwise explain the toolbar step.
Keep broad host permissions out of the production extension until their scope is agreed.

Before replacing the popup, complete the manual checks in
[scripts/side-panel-spike/README.md](../scripts/side-panel-spike/README.md), including revoked
permissions and the user's stable Chrome/Brave builds. The spike is discovery alongside
stage 1, not a production permission change or a completed stage 5 rollout.

Official references:
- [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
- [Chrome sidePanel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel)
- [Chrome permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions)
