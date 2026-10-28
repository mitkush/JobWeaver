/** Builds manifest.json for one JobWeaver server (ADR-0017). */

// Public half of the signing key, so every unpacked install gets the same extension ID
// (npdbpfgligiimfnoblngghbokehjbafm), which the server allows through EXTENSION_IDS.
export const PUBLIC_KEY =
  "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsyMURfwMgV4Jzi7qioIrr70nfGxvYy1JiKbv0CQPKxmEwxc2KbYM2rZW+UoToMZ6vYhc1ZUKP8qLH1b59KACLCwiN7m4o7UYo0DoF2wi0UFZ+leuf7yl7kr6dozgR0t2QsHHU3Tw6h/pMYiy22cSiBW2lNfAlncUN1+KsUPsOMe8PhC2EOFnIFuYv2/D/9EjdVMIDaIAO2zDekOUpaz7GUy1lRuxDCkEo8OerPr18BO3xcG6PJZ84av1a+RB2QLesgglwHrsqTJkia2faptIs2WLIwwcZB5+GmzKVKukhmYLQRyGS7jk+Q/vDjj9z8svasS893jP4PxiwbZcggf66QIDAQAB";

export const DEFAULT_ORIGIN = "https://jobweaver.duckdns.org";

/** Match patterns cannot name a port, so a local origin matches its host on any port. */
export function matchPattern(origin: string): string {
  const url = new URL(origin);
  return `${url.protocol}//${url.hostname}/*`;
}

export function buildManifest(origin: string, version: string) {
  const pattern = matchPattern(origin);
  return {
    manifest_version: 3,
    name: "JobWeaver",
    description: "Fills job application forms from your JobWeaver Drafts. You review and submit.",
    version,
    key: PUBLIC_KEY,
    minimum_chrome_version: "116",
    action: { default_title: "JobWeaver" },
    side_panel: { default_path: "popup.html" },
    background: { service_worker: "background.js", type: "module" },
    // activeTab: on the User's click, read the tab's address to suggest a Draft, and
    // (scripting) scan and fill that tab's form. No access to any other site.
    permissions: ["storage", "activeTab", "scripting", "sidePanel"],
    optional_permissions: ["downloads", "webNavigation"],
    optional_host_permissions: ["https://*/*", "http://*/*"],
    host_permissions: [pattern],
    externally_connectable: { matches: [pattern] },
  };
}
