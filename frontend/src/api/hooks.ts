import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  unwrap,
  uploadDocument,
  type DocumentKind,
  type Fact,
  type FactKind,
  type ApplicationStatus,
  type FeedQuery,
  type FollowUpRequest,
  type Me,
  type Preferences,
  type ProfileContent,
  type SavedAnswerInput,
  type WritingStyleInput,
} from "./client";

export const keys = {
  me: ["me"] as const,
  facts: ["facts"] as const,
  documents: ["documents"] as const,
  preferences: ["preferences"] as const,
  titleSuggestions: (titles: string[]) => ["preferences", "title-suggestions", ...titles] as const,
  sources: ["admin", "sources"] as const,
  runs: ["admin", "runs"] as const,
  boards: ["boards"] as const,
  feed: ["feed"] as const,
  runStartedAt: ["admin", "run-started-at"] as const,
  job: (id: string) => ["job", id] as const,
  applications: ["applications"] as const,
  reminders: ["reminders"] as const,
  company: (id: string) => ["company", id] as const,
  extensionConnections: ["extension", "connections"] as const,
  profile: ["profile"] as const,
  savedAnswers: ["saved-answers"] as const,
  writingStyle: ["writing-style"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET("/api/me")),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
}

export function useFacts() {
  return useQuery({ queryKey: keys.facts, queryFn: () => unwrap(api.GET("/api/facts")) });
}

export function useDocuments() {
  return useQuery({ queryKey: keys.documents, queryFn: () => unwrap(api.GET("/api/documents")) });
}

export function usePreferences() {
  return useQuery({
    queryKey: keys.preferences,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/preferences"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

/** Related titles to offer; only titles the User adds are ever searched. */
export function useTitleSuggestions(titles: string[]) {
  return useQuery({
    queryKey: keys.titleSuggestions(titles),
    queryFn: () => unwrap(api.GET("/api/preferences/title-suggestions", { params: { query: { titles } } })),
    enabled: titles.length > 0,
    placeholderData: (previous) => previous,
    staleTime: 5 * 60_000,
  });
}

function useSetMe() {
  const client = useQueryClient();
  return (me: Me) => client.setQueryData(keys.me, me);
}

export function useAcceptNotice() {
  const setMe = useSetMe();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/me/ai-notice")),
    onSuccess: setMe,
  });
}

export function useSetCountry() {
  const setMe = useSetMe();
  return useMutation({
    mutationFn: (country: string) => unwrap(api.PUT("/api/me/country", { body: { country } })),
    onSuccess: setMe,
  });
}

/** Refreshes everything the Fact Bank touches after a change. */
function useInvalidateFactBank() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.facts }),
      client.invalidateQueries({ queryKey: keys.documents }),
      client.invalidateQueries({ queryKey: keys.me }),
    ]);
}

export function useUploadDocument() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: ({ kind, file }: { kind: DocumentKind; file: File }) => uploadDocument(kind, file),
    onSettled: invalidate,
  });
}

export function useSaveTextDocument() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: (body: { kind: DocumentKind; text: string }) =>
      unwrap(api.POST("/api/documents/text", { body })),
    onSettled: invalidate,
  });
}

export function useRebuildFactBank() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/fact-bank/rebuild")),
    onSettled: invalidate,
  });
}

export function useCreateFact() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: (body: { kind: FactKind; group?: string; text: string }) =>
      unwrap(api.POST("/api/facts", { body })),
    onSuccess: invalidate,
  });
}

export function useUpdateFact() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; text?: string; group?: string }) =>
      unwrap(api.PATCH("/api/facts/{fact_id}", { params: { path: { fact_id: id } }, body })),
    onSuccess: invalidate,
  });
}

export function useDeleteFact() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/facts/{fact_id}", { params: { path: { fact_id: id } } })),
    onSuccess: invalidate,
  });
}

export function useMergeFacts() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: (body: { fact_ids: string[]; text: string }) =>
      unwrap(api.POST("/api/facts/merge", { body })),
    onSuccess: invalidate,
  });
}

export function useReviewFactBank() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/fact-bank/review")),
    onSuccess: invalidate,
  });
}

export function useDeleteFactBank() {
  const invalidate = useInvalidateFactBank();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/fact-bank")),
    onSuccess: invalidate,
  });
}

export function useSavePreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Preferences) => unwrap(api.PUT("/api/preferences", { body })),
    onSuccess: (saved) => {
      client.setQueryData(keys.preferences, saved);
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.me }),
        client.invalidateQueries({ queryKey: keys.feed }),
      ]);
    },
  });
}

export function useDisconnectGmail() {
  const setMe = useSetMe();
  return useMutation({ mutationFn: () => unwrap(api.DELETE("/api/gmail")), onSuccess: setMe });
}

/** Application Extension connections (ADR-0017). */
export function useExtensionConnections() {
  return useQuery({
    queryKey: keys.extensionConnections,
    queryFn: () => unwrap(api.GET("/api/extension/connections")),
  });
}

export function useRevokeExtensionConnection() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/extension/connections/{connection_id}", { params: { path: { connection_id: id } } })),
    onSettled: () => client.invalidateQueries({ queryKey: keys.extensionConnections }),
  });
}

/** What a connected extension can do; the approval page shows exactly this list. */
export function useExtensionScopes(enabled = true) {
  return useQuery({ queryKey: ["extension", "scopes"], queryFn: () => unwrap(api.GET("/api/extension/scopes")), enabled });
}

export function useApproveExtension() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { extension_id: string; challenge: string; scopes_version: number }) =>
      unwrap(api.POST("/api/extension/approve", { body })),
    onSettled: () => client.invalidateQueries({ queryKey: keys.extensionConnections }),
  });
}

/** The application profile the extension fills forms with; saving it is the review. */
export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: () => unwrap(api.GET("/api/profile")) });
}

export function useProfileSuggestion() {
  return useMutation({ mutationFn: () => unwrap(api.GET("/api/profile/suggestion")) });
}

export function useSaveProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { content: ProfileContent; expected_version: number }) => unwrap(api.PUT("/api/profile", { body })),
    onSuccess: (profile) => client.setQueryData(keys.profile, profile),
  });
}

export function useSavedAnswers() {
  return useQuery({ queryKey: keys.savedAnswers, queryFn: () => unwrap(api.GET("/api/saved-answers")) });
}

export function useSaveAnswer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: SavedAnswerInput }) =>
      id
        ? unwrap(api.PUT("/api/saved-answers/{answer_id}", { params: { path: { answer_id: id } }, body }))
        : unwrap(api.POST("/api/saved-answers", { body })),
    onSettled: () => client.invalidateQueries({ queryKey: keys.savedAnswers }),
  });
}

export function useDeleteAnswer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/saved-answers/{answer_id}", { params: { path: { answer_id: id } } })),
    onSettled: () => client.invalidateQueries({ queryKey: keys.savedAnswers }),
  });
}

export function useWritingStyle() {
  return useQuery({ queryKey: keys.writingStyle, queryFn: () => unwrap(api.GET("/api/me/writing-style")) });
}

export function useRebuildWritingStyle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/me/writing-style/rebuild")),
    onSuccess: (style) => client.setQueryData(keys.writingStyle, style),
  });
}

export function useSaveWritingStyle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: WritingStyleInput) => unwrap(api.PUT("/api/me/writing-style", { body })),
    onSuccess: (style) => client.setQueryData(keys.writingStyle, style),
  });
}

export function useClearWritingStyle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/me/writing-style")),
    onSettled: () => client.invalidateQueries({ queryKey: keys.writingStyle }),
  });
}

export function useDeleteAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/me")),
    onSuccess: () => client.clear(),
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSuccess: () => client.clear(),
  });
}

export function useSources() {
  return useQuery({ queryKey: keys.sources, queryFn: () => unwrap(api.GET("/api/admin/sources")) });
}

/** Refreshes every few seconds while a run is in progress (a manual run runs in the
 * background), and refreshes the Sources once it ends. */
export function useFetchRuns(page = 0, pageSize = 20) {
  const client = useQueryClient();
  const queryKey = [...keys.runs, page, pageSize];
  return useQuery({
    queryKey,
    queryFn: async () => {
      const previous = client.getQueryData<{ status: string }[]>(queryKey);
      const runs = await unwrap(api.GET("/api/admin/fetch-runs", { params: { query: { limit: pageSize + 1, offset: page * pageSize } } }));
      const wasRunning = previous?.some((run) => run.status === "running");
      if (wasRunning && !runs.some((run) => run.status === "running")) {
        void client.invalidateQueries({ queryKey: keys.sources });
      }
      return runs;
    },
    refetchInterval: (query) => {
      if (page > 0) return false;
      if (query.state.data?.some((run) => run.status === "running")) return 5000;
      // A run just started may not have written its first row yet.
      const startedAt = client.getQueryData<number>(keys.runStartedAt) ?? 0;
      return Date.now() - startedAt < 60_000 ? 3000 : false;
    },
  });
}

export function useUpdateSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      unwrap(api.PATCH("/api/admin/sources/{name}", { params: { path: { name } }, body: { enabled } })),
    onSuccess: (sources) => client.setQueryData(keys.sources, sources),
  });
}

export function useRunSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(api.POST("/api/admin/sources/{name}/run", { params: { path: { name } } })),
    onSuccess: (outcome) => {
      if (outcome.status === "started") client.setQueryData(keys.runStartedAt, Date.now());
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.sources }),
        client.invalidateQueries({ queryKey: keys.runs }),
      ]),
  });
}

export function useBoards() {
  return useQuery({ queryKey: keys.boards, queryFn: () => unwrap(api.GET("/api/ats-boards")) });
}

export function useAddBoard() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => unwrap(api.POST("/api/ats-boards", { body: { url } })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.boards }),
  });
}

export function useFeed(query: FeedQuery) {
  return useQuery({
    queryKey: [...keys.feed, query],
    queryFn: () => unwrap(api.GET("/api/feed", { params: { query } })),
    placeholderData: (previous) => previous,
  });
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: keys.job(jobId),
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
}

/** Grouping changes are shared: every Feed and Job view may have changed. */
function useInvalidateJobs() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.feed }),
      client.invalidateQueries({ queryKey: ["job"] }),
    ]);
}

export function useSetHidden() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: ({ jobId, hidden }: { jobId: string; hidden: boolean }) => {
      const params = { params: { path: { job_id: jobId } } };
      return unwrap(hidden ? api.POST("/api/feed/{job_id}/hide", params) : api.DELETE("/api/feed/{job_id}/hide", params));
    },
    onSettled: invalidate,
  });
}

export function useSetSaved() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: ({ jobId, saved }: { jobId: string; saved: boolean }) => {
      const params = { params: { path: { job_id: jobId } } };
      return unwrap(saved ? api.POST("/api/feed/{job_id}/save", params) : api.DELETE("/api/feed/{job_id}/save", params));
    },
    onSettled: invalidate,
  });
}

/** Sent once the Job page has loaded; cards appearing in the Feed never mark a Job viewed. */
export function useMarkViewed() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => unwrap(api.POST("/api/jobs/{job_id}/viewed", { params: { path: { job_id: jobId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.feed }),
  });
}

export function useConfirmDuplicate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (pairId: string) =>
      unwrap(api.POST("/api/possible-duplicates/{pair_id}/confirm", { params: { path: { pair_id: pairId } } })),
    // One of the two Jobs no longer exists: mark Job views stale without refetching the
    // open one, so the screen moves to the merged Job instead of flashing "not found".
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.feed }),
        client.invalidateQueries({ queryKey: ["job"], refetchType: "none" }),
      ]),
  });
}

export function useRejectDuplicate() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (pairId: string) =>
      unwrap(api.POST("/api/possible-duplicates/{pair_id}/reject", { params: { path: { pair_id: pairId } } })),
    onSettled: invalidate,
  });
}

export function useSplitPosting() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: ({ jobId, postingId }: { jobId: string; postingId: string }) =>
      unwrap(
        api.POST("/api/jobs/{job_id}/postings/{posting_id}/split", {
          params: { path: { job_id: jobId, posting_id: postingId } },
        }),
      ),
    onSettled: invalidate,
  });
}

export type { Fact };

// Applications (FR-F1 to FR-F3) ------------------------------------------------------------

export function useApplications() {
  return useQuery({ queryKey: keys.applications, queryFn: () => unwrap(api.GET("/api/applications")) });
}

export function useReminders() {
  return useQuery({ queryKey: keys.reminders, queryFn: () => unwrap(api.GET("/api/reminders")) });
}

export function useCompanyHistory(companyId: string) {
  return useQuery({
    queryKey: keys.company(companyId),
    queryFn: () =>
      unwrap(api.GET("/api/companies/{company_id}/applications", { params: { path: { company_id: companyId } } })),
  });
}

/** A status change shows on the tracker, reminders, Company history and Job cards. */
function useInvalidateApplications() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.applications }),
      client.invalidateQueries({ queryKey: keys.reminders }),
      client.invalidateQueries({ queryKey: ["company"] }),
      client.invalidateQueries({ queryKey: keys.feed }),
      client.invalidateQueries({ queryKey: ["job"] }),
    ]);
}

export function useSetApplicationStatus() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      unwrap(api.PATCH("/api/applications/{application_id}", { params: { path: { application_id: id } }, body: { status } })),
    onSettled: invalidate,
  });
}

export function useDismissReminder() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/applications/{application_id}/follow-up/dismiss", { params: { path: { application_id: id } } })),
    onSettled: invalidate,
  });
}

export function useFollowUp(id: string | null) {
  return useQuery({
    queryKey: ["follow-up", id],
    enabled: id !== null,
    queryFn: () =>
      unwrap(api.GET("/api/applications/{application_id}/follow-up", { params: { path: { application_id: id! } } })),
  });
}

export function useSendFollowUp() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: FollowUpRequest }) =>
      unwrap(api.POST("/api/applications/{application_id}/follow-up", { params: { path: { application_id: id } }, body })),
    onSuccess: invalidate,
  });
}

export function useAiUsage() {
  return useQuery({ queryKey: ["admin", "ai-usage"], queryFn: () => unwrap(api.GET("/api/admin/ai-usage")) });
}

export function useSetFollowUpDays() {
  const setMe = useSetMe();
  return useMutation({
    mutationFn: (days: number) => unwrap(api.PUT("/api/me/follow-up-days", { body: { days } })),
    onSuccess: setMe,
  });
}
