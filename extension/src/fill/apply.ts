/** Writes values into the page the way a person typing would, so React, Vue and plain
 * forms all notice them; and undoes only what the User has not changed since. Never
 * clicks, presses Enter or submits anything (ADR-0017). */

import type { FillItem, FillReport } from "./types";

type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
type Written =
  | { kind: "text" | "textarea" | "select"; previous: string; written: string }
  // Files are kept as the File objects themselves: the earlier upload comes back on undo,
  // and a different file with the same name still counts as the User's own change.
  | { kind: "file"; previous: File[]; written: File };

const OUTLINE = "2px solid #10b981";

function find(doc: Document, ref: string): Control | null {
  return Array.from(doc.querySelectorAll<Control>("[data-jobweaver-ref]")).find((el) => el.getAttribute("data-jobweaver-ref") === ref) ?? null;
}

/** Frameworks track the value through the prototype's setter; going around their own
 * property makes them see the change. */
function setValue(el: Control, value: string) {
  const proto = Object.getPrototypeOf(el) as object;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
}

function announce(el: Control) {
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: false }));
}

function decode(base64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function filesOf(el: HTMLInputElement): File[] {
  return Array.from(el.files ?? []);
}

function setFiles(el: HTMLInputElement, files: File[]) {
  const transfer = new (el.ownerDocument.defaultView!.DataTransfer)();
  for (const file of files) transfer.items.add(file);
  el.files = transfer.files;
}

function sameFile(a: File | undefined, b: File): boolean {
  return a === b || (a !== undefined && a.name === b.name && a.size === b.size && a.lastModified === b.lastModified && a.type === b.type);
}

export class Filler {
  private written = new Map<string, Written>();

  constructor(private readonly doc: Document) {}

  fill(items: FillItem[]): FillReport {
    const report: FillReport = { filled: [], failed: [] };
    const view = this.doc.defaultView!;
    for (const item of items) {
      const el = find(this.doc, item.ref);
      if (!el) {
        report.failed.push({ ref: item.ref, reason: "The field is no longer on the page" });
        continue;
      }
      try {
        if (item.kind === "file") {
          const input = el as HTMLInputElement;
          const previous = filesOf(input);
          const file = new view.File([decode(item.file.base64)], item.file.name, { type: item.file.type });
          setFiles(input, [file]);
          announce(input);
          const now = filesOf(input);
          if (now.length !== 1 || !sameFile(now[0], file)) throw new Error("The site did not accept the file");
          this.written.set(item.ref, { kind: "file", previous, written: now[0]! });
        } else if (item.kind === "select") {
          const select = el as HTMLSelectElement;
          const option = Array.from(select.options).find((o) => o.text.trim() === item.value);
          if (!option) throw new Error("That choice is not in the list");
          const previous = select.value;
          setValue(select, option.value);
          announce(select);
          this.written.set(item.ref, { kind: "select", previous, written: option.value });
        } else {
          const previous = el.value;
          el.focus();
          setValue(el, item.value);
          announce(el);
          this.written.set(item.ref, { kind: item.kind, previous, written: item.value });
        }
        el.style.outline = OUTLINE;
        el.setAttribute("data-jobweaver-filled", "true");
        report.filled.push(item.ref);
      } catch (error) {
        report.failed.push({ ref: item.ref, reason: (error as Error).message || "Could not fill this field" });
      }
    }
    return report;
  }

  /** Restores the previous value where the field still holds what JobWeaver wrote. */
  undo(): FillReport {
    const report: FillReport = { filled: [], failed: [] };
    for (const [ref, record] of this.written) {
      const el = find(this.doc, ref);
      if (!el) continue;
      const unchanged =
        record.kind === "file"
          ? (() => {
              const now = filesOf(el as HTMLInputElement);
              return now.length === 1 && sameFile(now[0], record.written);
            })()
          : el.value === record.written;
      if (!unchanged) {
        report.failed.push({ ref, reason: "You changed it after filling, so it was kept" });
        continue;
      }
      if (record.kind === "file") setFiles(el as HTMLInputElement, record.previous);
      else setValue(el, record.previous);
      announce(el);
      el.style.outline = "";
      el.removeAttribute("data-jobweaver-filled");
      report.filled.push(ref);
    }
    this.written.clear();
    return report;
  }
}
