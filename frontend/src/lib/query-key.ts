import { countryName } from "./countries";

/** "backend engineer@Bengaluru|IN|True" reads as "backend engineer · Bengaluru, India · remote". */
export function formatQueryKey(key: string | null | undefined): string {
  if (!key) return "";
  if (key === "all") return "all recent jobs";
  const [full, where = ""] = key.split("@");
  // A long keyword list is stored shortened, ending in "#<hash>".
  const keywords = full?.replace(/#[0-9a-f]{16}$/, "…");
  if (where === "any") return keywords ?? key;
  const [city, country, remote] = where.split("|");
  const place = [city, country ? countryName(country) : ""].filter(Boolean).join(", ");
  return [keywords, place, remote === "True" ? "remote" : ""].filter(Boolean).join(" · ");
}
