"use client";

import { ReactNode } from "react";
import { SWRConfig } from "swr";
import { ApiError } from "@/services/types";
import { ToastProvider } from "@/components/ui/Toast";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <SWRConfig
        value={{
          revalidateOnFocus: true,
          shouldRetryOnError: (err) => !(err instanceof ApiError && err.status !== 0),
          errorRetryInterval: 8000,
        }}
      >
        {children}
      </SWRConfig>
    </ToastProvider>
  );
}
