// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { Filler } from "../src/fill/apply";
import { adapterFor, GENERIC, GREENHOUSE, scanFields } from "../src/fill/fields";
import { optionFor, propose } from "../src/fill/plan";
import type { Field } from "../src/fill/types";

function load(name: string) {
  document.body.innerHTML = readFileSync(join(import.meta.dirname, "fixtures", name), "utf8");
}

function scan(adapter = GENERIC): Field[] {
  let n = 0;
  return scanFields(document, adapter, () => `r${++n}`);
}

const byLabel = (fields: Field[], label: string) => fields.find((f) => f.label.startsWith(label))!;

const profile = {
  first_name: "Asha",
  last_name: "Rao",
  email: "asha@example.com",
  phone: "+91 98765 43210",
  city: "Bengaluru",
  country: "IN",
  links: [
    { label: "linkedin", url: "https://linkedin.com/in/asha" },
    { label: "portfolio", url: "https://asha.dev" },
  ],
  employment: [{ employer: "Acme Corp", title: "Senior Developer", current: true }],
  education: [],
};
const files = { resume: "Asha_Acme_Backend.pdf", cover_letter: "Asha_Acme_Backend_Cover_Letter.pdf" };

describe("finding fields", () => {
  beforeEach(() => load("generic.html"));

  it("labels and classifies the applicant's own fields", () => {
    const fields = scan();
    const keys = Object.fromEntries(fields.map((f) => [f.label, f.key]));
    expect(keys).toMatchObject({
      "First name *": "first_name",
      "Last Name": "last_name",
      "Email address": "email",
      Phone: "phone",
      "LinkedIn profile URL": "linkedin",
      "Personal website": "website",
      City: "city",
      Country: "country",
      "Resume/CV": "resume",
      "Cover letter": "cover_letter",
    });
    expect(byLabel(fields, "First name").required).toBe(true);
    expect(byLabel(fields, "City").hasValue).toBe(true);
  });

  it("never guesses other people's details, sensitive answers or free-text questions", () => {
    const fields = scan();
    for (const label of ["Referrer name", "Expected salary", "Will you require visa sponsorship?", "Why do you want to work here?"]) {
      expect(byLabel(fields, label).key).toBeNull();
    }
  });

  it("skips hidden, disabled and password fields but keeps hidden file inputs", () => {
    const labels = scan().map((f) => f.label);
    expect(labels).not.toContain("Middle name");
    expect(labels.some((l) => l === "token" || l === "pw")).toBe(false);
    expect(labels.filter((l) => l === "Email")).toHaveLength(0);
    expect(labels).toContain("Resume/CV");
  });

  it("counts a real first option as a choice, and only placeholders as empty", () => {
    document.body.innerHTML = `
      <label for="a">Country</label><select id="a"><option value="US">United States</option><option value="IN">India</option></select>
      <label for="b">Country of residence</label><select id="b"><option value="">Select…</option><option value="IN">India</option></select>
      <label for="c">City</label><select id="c"><option value="x">-- Choose --</option><option value="BLR">Bengaluru</option></select>
      <label for="d">Location</label><select id="d"><option disabled selected>Pick one</option><option value="BLR">Bengaluru</option></select>`;
    const fields = scan();
    expect(fields.map((f) => f.hasValue)).toEqual([true, false, false, false]);
    // A populated dropdown is only replaced when the User ticks it.
    const country = propose(fields, profile, files).find((p) => p.label === "Country")!;
    expect(country).toMatchObject({ value: "India", overwrite: true });
  });

  it("uses Greenhouse's field ids on Greenhouse forms", () => {
    load("greenhouse.html");
    const adapter = adapterFor(new URL("https://job-boards.greenhouse.io/acme/jobs/4012345"));
    expect(adapter).toBe(GREENHOUSE);
    const fields = scan(adapter);
    expect(byLabel(fields, "Location (City)").key).toBe("location");
    expect(byLabel(fields, "First Name").key).toBe("first_name");
    expect(byLabel(fields, "LinkedIn Profile").key).toBe("linkedin");
    expect(byLabel(fields, "How did you hear about us?").key).toBeNull();
  });
});

describe("proposing values", () => {
  it("offers profile values and the Draft's PDFs, and marks filled fields as overwrites", () => {
    load("generic.html");
    const proposals = propose(scan(), profile, files);
    const byKey = Object.fromEntries(proposals.map((p) => [p.key, p]));
    expect(byKey.first_name?.value).toBe("Asha");
    expect(byKey.website?.value).toBe("https://asha.dev");
    expect(byKey.country?.value).toBe("India");
    expect(byKey.city).toMatchObject({ value: "Bengaluru", overwrite: true });
    expect(byKey.resume).toMatchObject({ value: files.resume, source: "draft" });
    expect(proposals.some((p) => p.label === "Referrer name")).toBe(false);
  });

  it("proposes only the PDFs before the profile is reviewed", () => {
    load("generic.html");
    expect(propose(scan(), null, files).map((p) => p.key).sort()).toEqual(["cover_letter", "resume"]);
  });

  it("picks a select option only when it is clear", () => {
    expect(optionFor(["Select…", "India", "Indonesia"], "India")).toBe("India");
    expect(optionFor(["IN", "US"], "India", "IN")).toBe("IN");
    expect(optionFor(["United States of America", "United States Minor Outlying Islands"], "United States")).toBeNull();
  });
});

describe("filling", () => {
  beforeEach(() => load("generic.html"));

  it("writes values so frameworks see them, outlines them and never submits", () => {
    const fields = scan();
    const submitted = vi.fn((e: Event) => e.preventDefault());
    document.querySelector("form")!.addEventListener("submit", submitted);
    const first = document.querySelector<HTMLInputElement>("#fn")!;
    const events: string[] = [];
    first.addEventListener("input", () => events.push("input"));
    first.addEventListener("change", () => events.push("change"));

    const filler = new Filler(document);
    const report = filler.fill([
      { ref: byLabel(fields, "First name").ref, kind: "text", value: "Asha" },
      { ref: byLabel(fields, "Country").ref, kind: "select", value: "India" },
    ]);
    expect(report.failed).toEqual([]);
    expect(first.value).toBe("Asha");
    expect(events).toEqual(["input", "change"]);
    expect(first.style.outline).toContain("solid");
    expect(document.querySelector<HTMLSelectElement>("#country")!.value).toBe("in");
    expect(submitted).not.toHaveBeenCalled();
  });

  it("reports fields that disappeared or choices that do not exist", () => {
    const fields = scan();
    const filler = new Filler(document);
    document.querySelector("#ln")!.remove();
    const report = filler.fill([
      { ref: byLabel(fields, "Last Name").ref, kind: "text", value: "Rao" },
      { ref: byLabel(fields, "Country").ref, kind: "select", value: "Atlantis" },
    ]);
    expect(report.filled).toEqual([]);
    expect(report.failed.map((f) => f.reason)).toEqual(["The field is no longer on the page", "That choice is not in the list"]);
  });

  it("undoes only values the User has not changed since", () => {
    const fields = scan();
    const filler = new Filler(document);
    filler.fill([
      { ref: byLabel(fields, "City").ref, kind: "text", value: "Bengaluru" },
      { ref: byLabel(fields, "Phone").ref, kind: "text", value: "+91 98765 43210" },
    ]);
    const phone = document.querySelector<HTMLInputElement>("#ph")!;
    phone.value = "+91 90000 00000"; // the User edits it after filling
    const report = filler.undo();
    expect(document.querySelector<HTMLInputElement>("#city")!.value).toBe("Mumbai");
    expect(phone.value).toBe("+91 90000 00000");
    expect(report.failed).toHaveLength(1);
  });

  describe("attachments", () => {
    // jsdom has no DataTransfer and a read-only files list; minimal stand-ins.
    class FakeTransfer {
      private list: File[] = [];
      items = { add: (file: File) => void this.list.push(file) };
      get files() {
        return Object.assign([...this.list], { item: (i: number) => this.list[i] ?? null }) as unknown as FileList;
      }
    }
    let input: HTMLInputElement;

    beforeEach(() => {
      Object.defineProperty(window, "DataTransfer", { value: FakeTransfer, configurable: true });
      input = document.querySelector<HTMLInputElement>("#cv")!;
      let current: FileList = new FakeTransfer().files;
      Object.defineProperty(input, "files", { get: () => current, set: (v: FileList) => (current = v), configurable: true });
    });

    const pdf = (ref: string) => ({
      ref,
      kind: "file" as const,
      file: { name: "Asha.pdf", type: "application/pdf", base64: btoa("%PDF-1.7") },
    });

    it("attaches the PDF", () => {
      const report = new Filler(document).fill([pdf(byLabel(scan(), "Resume/CV").ref)]);
      expect(report.failed).toEqual([]);
      expect(input.files?.[0]?.name).toBe("Asha.pdf");
    });

    it("brings back the User's own earlier file on undo", () => {
      const original = new File(["mine"], "original.pdf", { type: "application/pdf" });
      const before = new FakeTransfer();
      before.items.add(original);
      input.files = before.files;
      const filler = new Filler(document);
      filler.fill([pdf(byLabel(scan(), "Resume/CV").ref)]);
      expect(input.files?.[0]?.name).toBe("Asha.pdf");
      const report = filler.undo();
      expect(report.failed).toEqual([]);
      expect(input.files?.[0]).toBe(original);
    });

    it("keeps a file the User attached after filling, even with the same name", () => {
      const filler = new Filler(document);
      filler.fill([pdf(byLabel(scan(), "Resume/CV").ref)]);
      const theirs = new FakeTransfer();
      theirs.items.add(new File(["their own edit"], "Asha.pdf", { type: "application/pdf" }));
      input.files = theirs.files;
      const report = filler.undo();
      expect(report.failed).toHaveLength(1);
      expect(input.files?.[0]?.size).toBe("their own edit".length);
    });
  });
});

it("offers reviewed draft text only for a background-and-interest question", () => {
  document.body.innerHTML = `<form><label for="intro">Please tell us a little about your background and why you're interested in this role.*</label><textarea id="intro"></textarea><label for="salary">Background and salary interest</label><textarea id="salary"></textarea></form>`;
  const fields = scan();
  expect(fields[0]?.key).toBe("background_answer");
  expect(fields[1]?.key).toBeNull();
  const proposed = propose(fields, profile, { ...files, background_answer: "I built Python APIs and would like to apply that experience here." });
  expect(proposed).toHaveLength(1);
  expect(proposed[0]).toMatchObject({ source: "draft", reviewRequired: true });
  const filler = new Filler(document);
  filler.fill([{ ref: fields[0]!.ref, kind: "textarea", value: proposed[0]!.value }]);
  expect(document.querySelector("textarea")?.value).toContain("Python APIs");
  filler.undo();
  expect(document.querySelector("textarea")?.value).toBe("");
});

it("leaves no-AI forms and too-short fields for manual answers", () => {
  document.body.innerHTML = `<form><p>Do not use AI to answer.</p><label for="a">Your background and why you're interested</label><textarea id="a"></textarea></form>`;
  expect(scan()[0]?.key).toBeNull();
  document.querySelector("p")!.remove();
  document.querySelector("textarea")!.maxLength = 5;
  const fields = scan();
  expect(propose(fields, profile, { ...files, background_answer: "A longer answer" })).toEqual([]);
});

it("marks the applicant's free-text questions, sensitive ones and no-AI forms", () => {
  document.body.innerHTML = `<form>
    <label for="why">Why do you want to work here?</label><textarea id="why"></textarea>
    <label for="visa">Will you require visa sponsorship to work here?</label><input id="visa">
    <label for="ref">Who referred you to this role?</label><textarea id="ref"></textarea>
    <label for="nick">Preferred name</label><input id="nick">
  </form>`;
  const fields = scan();
  expect(byLabel(fields, "Why do you").question).toBe(true);
  expect(byLabel(fields, "Why do you").sensitive).toBe(false);
  expect(byLabel(fields, "Will you require")).toMatchObject({ question: true, sensitive: true, noAi: false });
  expect(byLabel(fields, "Who referred").question).toBeUndefined();
  expect(byLabel(fields, "Preferred name").question).toBeUndefined();
  document.querySelector("form")!.insertAdjacentHTML("afterbegin", "<p>Answers must not be generated by AI.</p>");
  expect(scan().every((f) => !f.question || f.noAi)).toBe(true);
});
