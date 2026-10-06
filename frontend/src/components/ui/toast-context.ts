import { createContext, useContext } from "react";

export type Toast = { id: number; tone: "success" | "error"; message: string };

export const ToastContext = createContext<(tone: Toast["tone"], message: string) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}
