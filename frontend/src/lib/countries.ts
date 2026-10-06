// ISO 3166-1 alpha-2 codes; names come from the browser so they stay localised.
const CODES =
  "AE AR AT AU BD BE BG BR CA CH CL CN CO CY CZ DE DK EE EG ES FI FR GB GR HK HR HU ID IE IL IN IS IT JP KE KR LI LK LT LU LV MA MT MX MY NG NL NO NP NZ PE PH PK PL PT QA RO RS SA SE SG SI SK TH TR TW UA US VN ZA".split(
    " ",
  );

const names = new Intl.DisplayNames(["en"], { type: "region" });

export function countryName(code: string): string {
  return names.of(code.toUpperCase()) ?? code.toUpperCase();
}

export const COUNTRIES: { code: string; name: string }[] = CODES.map((code) => ({
  code,
  name: countryName(code),
})).sort((a, b) => a.name.localeCompare(b.name));
