import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  unwrap,
  uploadDocument,
  type DocumentKind,
  type Fact,
  type FactKind,
  type Me,
  type Preferences,
} from "./client";

export const keys = {
  me: ["me"] as const,
  facts: ["facts"] as const,
  documents: ["documents"] as const,
  preferences: ["preferences"] as const,
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
      return client.invalidateQueries({ queryKey: keys.me });
    },
  });
}

export function useDisconnectGmail() {
  const setMe = useSetMe();
  return useMutation({ mutationFn: () => unwrap(api.DELETE("/api/gmail")), onSuccess: setMe });
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

export type { Fact };
