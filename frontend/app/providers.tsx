"use client";

import { ReactNode } from "react";
import { SWRConfig } from "swr";
import { ApiError } from "@/services/types";
import { ToastProvider } from "@/components/ui/Toast";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { AuthProvider } from "@/lib/auth";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
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
      </AuthProvider>
    </ThemeProvider>
  );
}
