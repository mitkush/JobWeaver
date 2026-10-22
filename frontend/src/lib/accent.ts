export type Accent = "pink" | "purple" | "lime" | "amber" | "cyan";

// Each area of the app has its own accent, as onebrain.run gives each section a colour.
const ACCENTS: [string, Accent][] = [
  ["/feed", "pink"],
  ["/jobs", "pink"],
  ["/drafts", "purple"],
  ["/fact-bank", "purple"],
  ["/preferences", "lime"],
  ["/applications", "amber"],
  ["/companies", "amber"],
  ["/settings", "cyan"],
  ["/admin", "cyan"],
];

export function accentFor(pathname: string): Accent {
  return ACCENTS.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "pink";
}
