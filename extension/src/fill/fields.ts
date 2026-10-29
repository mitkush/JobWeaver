/** Finds the fillable controls on a page and what each one asks for (ADR-0017).
 * Deterministic: labels, autocomplete tokens and field names, never AI. A field whose
 * meaning is unclear gets no key and stays manual work for the User. */

import type { Field, FieldKey, FieldKind } from "./types";

const TEXT_TYPES = new Set(["", "text", "email", "tel", "url", "search", "number"]);

// Questions about someone else, or answers JobWeaver must not guess (ADR-0017).
const NOT_THE_APPLICANT =
  /\b(refer(r?al|red|rer)?|reference|emergency|recruiter|hiring manager|manager'?s|spouse|parent|guardian|friend|employee)\b/;
const SENSITIVE =
  /\b(citizenship|nationality|authori[sz](ed|ation)|sponsor(ship)?|visa|salary|compensation|notice|gender|race|ethnic|veteran|disability|pronoun|date of birth|birth|age)\b/;

// A form that asks applicants not to use AI gets Fact notes only (ADR-0017).
export const NO_AI =
  /\b(no (?:use of )?ai|(?:do not|don.t|must not) use (?:ai|artificial intelligence)|not (?:be )?(?:written|generated) (?:by|with|using) (?:ai|artificial intelligence)|without (?:using )?(?:ai|artificial intelligence))\b/i;

const AUTOCOMPLETE: Record<string, FieldKey> = {
  "given-name": "first_name",
  "family-name": "last_name",
  name: "full_name",
  email: "email",
  tel: "phone",
  "tel-national": "phone",
  "address-level2": "city",
  country: "country",
  "country-name": "country",
  organization: "current_company",
  "organization-title": "current_title",
};

// Checked in order; the first match wins. Patterns run on the normalised label.
const LABEL_RULES: [FieldKey, RegExp][] = [
  ["linkedin", /linked\s?in/],
  ["github", /git\s?hub/],
  ["portfolio", /portfolio/],
  ["first_name", /\b(first|given|fore)\s?name\b/],
  ["last_name", /\b(last|family)\s?name\b|\bsurname\b/],
  ["full_name", /^(your |full |legal |full legal )?name$/],
  ["email", /\be-?mail\b/],
  ["phone", /\b(phone|mobile|telephone|cell)\b|contact number/],
  ["current_company", /\bcurrent (company|employer)\b|\bpresent employer\b|^(company|employer)$/],
  ["current_title", /\bcurrent (job )?(title|role|position|designation)\b|^(job )?title$/],
  ["school", /\b(school|university|college)\b/],
  ["degree", /^(highest )?(degree|qualification)$/],
  ["city", /^(current )?city$|\bcity of residence\b/],
  ["country", /^(current )?country( of residence)?$/],
  ["location", /^(current )?location$|where are you (based|located)|\bcurrent location\b/],
  ["website", /\b(website|personal site|blog)\b/],
];

// Field names and ids: "first_name", "firstName", "applicant.email".
const NAME_RULES: [FieldKey, RegExp][] = [
  ["first_name", /(^|[._-])(first_?name|firstname|fname|given_?name)$/],
  ["last_name", /(^|[._-])(last_?name|lastname|lname|family_?name|surname)$/],
  ["email", /(^|[._-])e_?mail$/],
  ["phone", /(^|[._-])(phone|mobile|tel)(_?number)?$/],
  ["linkedin", /linkedin/],
  ["github", /github/],
];

export function normalise(text: string): string {
  return text
    .replace(/\*/g, " ")
    .replace(/\((required|optional)\)/gi, " ")
    .replace(/[:?]+\s*$/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

function textOf(doc: Document, ids: string): string {
  return ids
    .split(/\s+/)
    .map((id) => doc.getElementById(id)?.textContent ?? "")
    .join(" ");
}

/** What a person reading the form would call this field. */
export function labelOf(el: Control): string {
  const doc = el.ownerDocument;
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = textOf(doc, labelledBy).trim();
    if (text) return text;
  }
  const aria = el.getAttribute("aria-label");
  if (aria?.trim()) return aria;
  if (el.id) {
    const forLabel = Array.from(doc.querySelectorAll("label[for]")).find((l) => l.getAttribute("for") === el.id);
    if (forLabel?.textContent?.trim()) return forLabel.textContent;
  }
  const wrapping = el.closest("label");
  if (wrapping) {
    const clone = wrapping.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("input, select, textarea, option").forEach((n) => n.remove());
    if (clone.textContent?.trim()) return clone.textContent;
  }
  if ("placeholder" in el && el.placeholder) return el.placeholder;
  const legend = el.closest("fieldset")?.querySelector("legend")?.textContent;
  if (legend?.trim()) return legend;
  return el.name || el.id || "";
}

export function kindOf(el: Element): FieldKind | null {
  if (el instanceof el.ownerDocument.defaultView!.HTMLTextAreaElement) return "textarea";
  if (el instanceof el.ownerDocument.defaultView!.HTMLSelectElement) return "select";
  if (el instanceof el.ownerDocument.defaultView!.HTMLInputElement) {
    const type = (el.getAttribute("type") ?? "").toLowerCase();
    if (type === "file") return "file";
    if (TEXT_TYPES.has(type)) return "text";
  }
  return null;
}

function formTextOf(el: Element): string {
  return el.closest("form")?.textContent ?? el.ownerDocument.body.textContent ?? "";
}

/** A free-text question about the applicant that no profile value answers: a text area,
 * or a single-line field whose label is a real question. */
export function questionOf(el: Control, kind: FieldKind, label: string, key: FieldKey | null) {
  if (key || (kind !== "textarea" && kind !== "text")) return null;
  const text = normalise(label);
  if (!text || NOT_THE_APPLICANT.test(text)) return null;
  const asks = kind === "textarea" || (label.trim().endsWith("?") && text.split(" ").length >= 4);
  if (!asks) return null;
  return { question: true, sensitive: SENSITIVE.test(text), noAi: NO_AI.test(formTextOf(el)) };
}

/** The profile value a field asks for, or null when it is not clearly one of them. */
export function classify(el: Control, kind: FieldKind, label: string): FieldKey | null {
  const text = normalise(label);
  if (NOT_THE_APPLICANT.test(text) || SENSITIVE.test(text)) return null;
  if (kind === "file") {
    if (/cover\s?letter/.test(text)) return "cover_letter";
    if (/\b(resume|résumé|cv|curriculum)\b/.test(text)) return "resume";
    return null;
  }
  if (kind === "textarea") {
    // Reuse the chosen job-specific letter only for this combined question.
    if (NO_AI.test(formTextOf(el))) return null;
    return /\bbackground\b/.test(text) && /\b(why|interest|interested|motivation)\b/.test(text)
      ? "background_answer" : null;
  }
  const autocomplete = (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/).pop() ?? "";
  if (AUTOCOMPLETE[autocomplete]) return AUTOCOMPLETE[autocomplete];
  for (const [key, pattern] of LABEL_RULES) if (pattern.test(text)) return key;
  const name = `${el.getAttribute("name") ?? ""} ${el.id}`.toLowerCase();
  for (const part of name.split(/\s+/).filter(Boolean)) {
    for (const [key, pattern] of NAME_RULES) if (pattern.test(part)) return key;
  }
  return null;
}

function hidden(el: Element, kind: FieldKind): boolean {
  if (el.closest("[hidden], [aria-hidden='true']")) return true;
  // File inputs are often visually hidden behind a styled button but still work.
  if (kind === "file") return false;
  const view = el.ownerDocument.defaultView;
  for (let node: Element | null = el; node; node = node.parentElement) {
    const style = view?.getComputedStyle(node);
    if (style && (style.display === "none" || style.visibility === "hidden")) return true;
  }
  return false;
}

const PLACEHOLDER = /^(-+|—+|select\b|choose\b|please (select|choose)|pick\b|none selected|\(none\))/i;

/** "Select…", "-- Choose --", or an empty or disabled option: not a real choice. The
 * position in the list says nothing: a list may start with a real country. */
export function isPlaceholder(option: HTMLOptionElement): boolean {
  const text = option.text.trim();
  return option.disabled || option.value === "" || text === "" || PLACEHOLDER.test(text);
}

export function hasValue(el: Control, kind: FieldKind): boolean {
  if (kind === "file") return ((el as HTMLInputElement).files?.length ?? 0) > 0;
  if (kind === "select") {
    const option = (el as HTMLSelectElement).options[(el as HTMLSelectElement).selectedIndex];
    return Boolean(option && !isPlaceholder(option));
  }
  return el.value.trim() !== "";
}

export type Adapter = {
  name: string;
  matches: (url: URL) => boolean;
  /** A key for fields the adapter knows by id or name, else undefined for the generic rules. */
  keyFor?: (el: Control) => FieldKey | null | undefined;
};

export const GENERIC: Adapter = { name: "generic", matches: () => true };

/** Greenhouse application forms, hosted (boards.greenhouse.io, job-boards.greenhouse.io). */
export const GREENHOUSE: Adapter = {
  name: "greenhouse",
  matches: (url) => /(^|\.)greenhouse\.io$/.test(url.hostname),
  keyFor: (el) =>
    ({
      first_name: "first_name",
      last_name: "last_name",
      email: "email",
      phone: "phone",
      resume: "resume",
      cover_letter: "cover_letter",
      "candidate-location": "location",
      country: "country",
    })[el.id] as FieldKey | undefined,
};

export const ADAPTERS = [GREENHOUSE, GENERIC];

export function adapterFor(url: URL): Adapter {
  return ADAPTERS.find((a) => a.matches(url)) ?? GENERIC;
}

/** Every fillable control, tagged with a ref the fill step uses to find it again. */
export function scanFields(doc: Document, adapter: Adapter, newRef: () => string): Field[] {
  const fields: Field[] = [];
  for (const el of doc.querySelectorAll<Control>("input, textarea, select")) {
    const kind = kindOf(el);
    if (!kind || el.disabled || ("readOnly" in el && el.readOnly) || hidden(el, kind)) continue;
    const label = labelOf(el).replace(/\s+/g, " ").trim().slice(0, 300);
    const known = adapter.keyFor?.(el);
    const key = known !== undefined ? known : classify(el, kind, label);
    const ref = el.getAttribute("data-jobweaver-ref") ?? newRef();
    const question = questionOf(el, kind, label, key);
    el.setAttribute("data-jobweaver-ref", ref);
    fields.push({
      ref,
      kind,
      label: label || "(no label)",
      key,
      required: el.required || el.getAttribute("aria-required") === "true",
      hasValue: hasValue(el, kind),
      ...("maxLength" in el && el.maxLength > 0 ? { maxLength: el.maxLength } : {}),
      ...(question ?? {}),
      ...(kind === "select"
        ? { options: Array.from((el as HTMLSelectElement).options, (o) => o.text.trim()).slice(0, 400) }
        : {}),
    });
  }
  return fields;
}
