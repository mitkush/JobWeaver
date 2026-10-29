/** Shared between the content script, the service worker and the popup. Messages carry
 * only these plain shapes, never DOM nodes. */

export type FieldKey =
  | "first_name"
  | "last_name"
  | "full_name"
  | "email"
  | "phone"
  | "city"
  | "country"
  | "location"
  | "linkedin"
  | "github"
  | "portfolio"
  | "website"
  | "current_company"
  | "current_title"
  | "school"
  | "degree"
  | "resume"
  | "cover_letter"
  | "background_answer";

export type FieldKind = "text" | "textarea" | "select" | "file";

export type Field = {
  /** data-jobweaver-ref given to the element during this scan. */
  ref: string;
  kind: FieldKind;
  label: string;
  key: FieldKey | null;
  required: boolean;
  /** The User or the page already filled it; overwriting needs an explicit choice. */
  hasValue: boolean;
  options?: string[];
  maxLength?: number;
  /** A free-text question about the applicant, answered only after the User reviews it. */
  question?: boolean;
  /** Work authorisation, salary, notice and similar: only ever a Saved Answer. */
  sensitive?: boolean;
  /** The form asks for answers not written by AI: Fact notes only, never a Suggestion. */
  noAi?: boolean;
};

export type Scan = { scanId: string; url: string; adapter: string; fields: Field[] };

export type FillItem =
  | { ref: string; kind: "text" | "textarea" | "select"; value: string }
  | { ref: string; kind: "file"; file: { name: string; type: string; base64: string } };

export type FillReport = {
  filled: string[];
  failed: { ref: string; reason: string }[];
};
