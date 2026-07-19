"use client";

import { ReactNode } from "react";
import { SWRConfig } from "swr";
import { ApiError } from "@/services/types";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: true,
        shouldRetryOnError: (err) => !(err instanceof ApiError && err.status !== 0),
        errorRetryInterval: 8000,
      }}
    >
      {children}
    </SWRConfig>
  );
}
