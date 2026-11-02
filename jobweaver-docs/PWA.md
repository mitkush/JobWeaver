# Install JobWeaver

Settings has an Install JobWeaver card. Brave/Chrome offer an Install app button when the browser emits its install prompt; otherwise the card explains the browser menu. Safari users can add the site to the Dock (Mac) or Home Screen (iPhone/iPad). Installed launches open `/feed` in a standalone window and use the existing sign-in flow.

This follows ShrifflePayroll's manifest, icons and deferred install prompt approach. The prompt is registered before React mounts, remains available when Settings opens later, and is consumed once. Browser confirmation controls the installed status. A declined/failed prompt gives manual installation instructions.

This release requires internet access. It adds no service worker, offline storage, background sync or push notifications. An installable web manifest is sufficient for current supported browsers; offline behavior is a separate feature. Resume editing, saving, generating and loading account data continue to use the server. Application filling remains in the browser extension on employer pages.

## Deployment

Deploy the regular frontend and backend image. The static build includes `/manifest.webmanifest`, `/pwa-icon-192.png`, `/pwa-icon-512.png` and `/apple-touch-icon.png`. The manifest is served as `application/manifest+json` with `Cache-Control: no-cache`; a missing manifest returns 404 rather than the SPA HTML. HTTPS is already provided by the normal production setup. No migration or new dependency is needed.

## Verification

Frontend coverage exercises an offer emitted before Settings mounts, dismissal/retry, failed prompts and browser confirmation. Backend coverage checks manifest MIME type, cache policy and missing-file behavior. Browser verification uses a local production preview; OS installation remains a manual acceptance step after deployment.

Validated locally: 151 frontend tests, both backend SPA/static tests, frontend lint/typecheck/build and backend lint/format passed. Brave in a throwaway normal profile reported zero installability errors, correct 192px/512px icons and no phone-width overflow or page JavaScript errors. Private browser contexts refuse installation, as expected. Safari/iPhone OS installation has not been performed.

Browser installation background: https://web.dev/articles/install-criteria
