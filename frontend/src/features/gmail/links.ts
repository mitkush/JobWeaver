export function gmailConnectHref(next: string) {
  return `/api/gmail/connect?next=${encodeURIComponent(next)}`;
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
