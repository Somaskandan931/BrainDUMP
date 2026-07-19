"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/format";

interface ToastItem {
  id: number;
  message: string;
}

interface ToastContextValue {
  /** Show a friendly error toast instead of letting the failure crash the page. */
  error: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextToastId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const error = useCallback(
    (message: string) => {
      const id = nextToastId++;
      setToasts((current) => [...current, { id, message }]);
      // Auto-dismiss so a stale backend-down banner doesn't linger forever.
      setTimeout(() => dismiss(id), 6000);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ error }), [error]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2 rounded-md border border-hairline bg-surface-raised px-3 py-2.5 text-[13px] text-ink shadow-lg"
            )}
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-500" />
            <p className="flex-1">{t.message}</p>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 text-ink-faint hover:text-ink"
              aria-label="Dismiss"
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fail soft: a missing provider shouldn't crash the caller, just log.
    return {
      error: (message: string) => console.error("[toast]", message),
    };
  }
  return ctx;
}
