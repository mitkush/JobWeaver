import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { JobDescription } from "@/features/feed/JobDescription";

it("renders headings, paragraphs and lists from plain text without running HTML", () => {
  render(
    <JobDescription
      text={"About the role\nBuild billing APIs.\nResponsibilities\n- Own the ledger\n• Review code\n<img src=x onerror=alert(1)>"}
    />,
  );
  expect(screen.getByRole("heading", { name: "About the role" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Responsibilities" })).toBeInTheDocument();
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Own the ledger", "Review code"]);
  // Markup in an advert is shown as text, never parsed.
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
});

it("says when there is no description", () => {
  render(<JobDescription text="   " />);
  expect(screen.getByText("No description was provided.")).toBeInTheDocument();
});
