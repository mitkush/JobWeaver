import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useAddBoard, useBoards } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";

const ATS_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
  recruitee: "Recruitee",
  workday: "Workday",
};

/** Company boards are learned from apply links; users can add more (FR-B7). */
export function CompanyBoards() {
  const boards = useBoards();
  const add = useAddBoard();
  const [url, setUrl] = useState("");
  const toast = useToast();

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const board = await add.mutateAsync(url);
      toast("success", `${ATS_LABELS[board.ats] ?? board.ats} board for ${board.slug} added`);
      setUrl("");
    } catch {
      // The error is shown inline below.
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://boards.greenhouse.io/company"
          aria-label="Company job board link"
        />
        <Button
          type="submit"
          variant="secondary"
          className="shrink-0 whitespace-nowrap"
          loading={add.isPending}
          disabled={url.trim().length < 8}
        >
          <Plus className="size-4" aria-hidden />
          Add board
        </Button>
      </form>
      {add.isError && <Alert tone="error">{add.error.message}</Alert>}
      {boards.data && boards.data.length > 0 ? (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm dark:divide-slate-800 dark:border-slate-800">
          {boards.data.map((board) => (
            <li key={board.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
              <div>
                <span className="font-medium">{board.company ?? board.slug}</span>
                <span className="ml-2 text-xs text-slate-500">
                  {ATS_LABELS[board.ats] ?? board.ats}
                  {board.discovered_from === "apply_url" ? " · found automatically" : " · added by hand"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {board.open_postings > 0 && <span className="text-xs text-slate-500">{board.open_postings} open</span>}
                {!board.enabled ? (
                  <Badge>Not found</Badge>
                ) : board.fetched ? (
                  <Badge tone="success">Fetched daily</Badge>
                ) : (
                  <Badge>Source turned off</Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">
          No boards yet. JobWeaver adds them automatically when a job's apply link points to one.
        </p>
      )}
    </div>
  );
}
