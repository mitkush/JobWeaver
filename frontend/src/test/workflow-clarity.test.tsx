import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { SkillGaps } from "@/features/feed/SkillGaps";
import { SourceBadges } from "@/features/feed/SourceBadges";
import { GenerationProgress } from "@/features/drafts/GenerationProgress";

afterEach(() => vi.useRealTimers());

it("shows the first four matched and missing skills before expanding each remainder", async () => {
  render(<SkillGaps compact gaps={["Go", "Rust", "C", "Java", "Ruby", "SQL"]} matches={["Python", "Rails", "Docker", "Redis", "Kafka"]} />);
  expect(screen.getByText(/Go, Rust, C, Java/)).toBeVisible();
  expect(screen.getByText(/Python, Rails, Docker, Redis/)).toBeVisible();
  expect(screen.getByText("Ruby, SQL")).not.toBeVisible();
  expect(screen.getByText("Kafka")).not.toBeVisible();
  await userEvent.click(screen.getByLabelText("Show 2 more skills not in your Fact Bank"));
  expect(screen.getByText("Ruby, SQL")).toBeVisible();
  expect(screen.getByText("Kafka")).not.toBeVisible();
  await userEvent.click(screen.getByLabelText("Show 1 more matched skills"));
  expect(screen.getByText("Kafka")).toBeVisible();
});

it("lets readers expand every source", async () => {
  render(<SourceBadges compact sources={["One", "Two", "Three"].map(label => ({ name: label, label }))} />);
  expect(screen.getByText("Three")).not.toBeVisible();
  await userEvent.click(screen.getByText("Available on 3 sources"));
  expect(screen.getByText("Three")).toBeVisible();
});

it("updates real provider progress without restarting the local waiting clock", () => {
  vi.useFakeTimers();
  const view = render(<MemoryRouter><GenerationProgress jobId="1" progress="Trying Claude" /></MemoryRouter>);
  act(() => vi.advanceTimersByTime(65000));
  view.rerender(<MemoryRouter><GenerationProgress jobId="1" progress="Falling back to Gemini" /></MemoryRouter>);
  expect(screen.getByRole("status")).toHaveTextContent("Falling back to Gemini");
  expect(screen.getByText(/Waiting here: 1m 5s/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Back to Job" })).toHaveAttribute("href", "/jobs/1");
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
