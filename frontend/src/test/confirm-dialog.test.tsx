import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";

it("opens as a modal and Escape cancels", async () => {
  const showModal = vi.fn(function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  });
  const original = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = showModal;
  const onCancel = vi.fn();
  try {
    render(
      <ConfirmDialog open title="Delete?" confirmLabel="Delete" onConfirm={() => {}} onCancel={onCancel}>
        Gone for good.
      </ConfirmDialog>,
    );
    expect(showModal).toHaveBeenCalledTimes(1);
    const dialog = screen.getByRole("dialog");
    dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    expect(onCancel).toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  } finally {
    HTMLDialogElement.prototype.showModal = original;
  }
});
