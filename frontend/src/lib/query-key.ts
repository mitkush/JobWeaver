import { countryName } from "./countries";

/** "backend engineer@Bengaluru|IN|True" reads as "backend engineer · Bengaluru, India · remote". */
export function formatQueryKey(key: string | null | undefined): string {
  if (!key) return "";
  if (key === "all") return "all recent jobs";
  const [keywords, where = ""] = key.split("@");
  if (where === "any") return keywords ?? key;
  const [city, country, remote] = where.split("|");
  const place = [city, country ? countryName(country) : ""].filter(Boolean).join(", ");
  return [keywords, place, remote === "True" ? "remote" : ""].filter(Boolean).join(" · ");
}
