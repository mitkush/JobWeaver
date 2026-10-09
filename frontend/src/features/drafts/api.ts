import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/api/client";
import { keys } from "@/api/hooks";

export type Draft = Schemas["DraftOut"];
export type Content = Schemas["DraftContent"];
export type Line = Schemas["DraftLine"];
export type Version = Schemas["VersionOut"];
export type Part = "resume" | "cover_letter" | "email_body";

const draftKey = (id: string) => ["draft", id] as const;

export function useCreateDraft() {
  return useMutation({
    mutationFn: (jobId: string) => unwrap(api.POST("/api/drafts", { body: { job_id: jobId } })),
  });
}

export function useDraft(id: string) {
  return useQuery({
    queryKey: draftKey(id),
    queryFn: () => unwrap(api.GET("/api/drafts/{draft_id}", { params: { path: { draft_id: id } } })),
    refetchInterval: (query) => ["queued", "generating"].includes(query.state.data?.state ?? "") ? 1000 : false,
  });
}

export function useVersions(id: string) {
  return useQuery({
    queryKey: ["draft", id, "versions"],
    queryFn: () => unwrap(api.GET("/api/drafts/{draft_id}/versions", { params: { path: { draft_id: id } } })),
  });
}

export function useDraftDiff(id: string, number: number, enabled: boolean) {
  return useQuery({
    queryKey: ["draft", id, "diff", number],
    queryFn: () => unwrap(api.GET("/api/drafts/{draft_id}/diff", { params: { path: { draft_id: id }, query: { number } } })),
    enabled,
  });
}

export function useDraftActions(id: string) {
  const client = useQueryClient();
  const refresh = async (draft?: Draft) => {
    if (draft) client.setQueryData(draftKey(id), draft);
    await Promise.all([
      client.invalidateQueries({ queryKey: ["draft", id, "versions"] }),
      client.invalidateQueries({ queryKey: keys.feed }),
      client.invalidateQueries({ queryKey: ["job"] }),
      ...(draft ? [] : [client.invalidateQueries({ queryKey: draftKey(id) })]),
    ]);
  };
  const save = useMutation({
    mutationFn: (body: Schemas["DraftSave"]) => unwrap(api.PUT("/api/drafts/{draft_id}", { params: { path: { draft_id: id } }, body })),
    onSuccess: refresh,
  });
  const recheck = useMutation({
    mutationFn: (expected_version: number) => unwrap(api.POST("/api/drafts/{draft_id}/recheck", { params: { path: { draft_id: id } }, body: { expected_version } })),
    onSuccess: refresh,
  });
  const chat = useMutation({
    mutationFn: (body: Schemas["DraftChat"]) => unwrap(api.POST("/api/drafts/{draft_id}/chat", { params: { path: { draft_id: id } }, body })),
    onSuccess: refresh,
  });
  const restore = useMutation({
    mutationFn: (body: Schemas["RestoreVersion"]) => unwrap(api.POST("/api/drafts/{draft_id}/restore", { params: { path: { draft_id: id } }, body })),
    onSuccess: refresh,
  });
  const retry = useMutation({
    mutationFn: () => unwrap(api.POST("/api/drafts/{draft_id}/retry", { params: { path: { draft_id: id } } })),
    onSuccess: refresh,
  });
  const applied = useMutation({
    mutationFn: (number: number) => unwrap(api.POST("/api/drafts/{draft_id}/applied", { params: { path: { draft_id: id } }, body: { expected_version: number } })),
    onSuccess: () => refresh(),
  });
  return { save, recheck, chat, restore, retry, applied, refresh };
}

export function pdfHref(id: string, kind: "resume" | "cover_letter", number: number, template = "standard") {
  return `/api/drafts/${encodeURIComponent(id)}/pdf?` + new URLSearchParams({ kind, number: String(number), template });
}
