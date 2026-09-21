"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/services/types";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: Record<string, unknown>) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

/**
 * `onError` receives the server's message (e.g. "An account with this email already exists.
 * Sign in with your email and password instead.") so the page can show it -- without it a
 * failed Google sign-in would do nothing visible.
 *
 * Visually this renders our own styled button (to match GithubButton and
 * the rest of the app) with Google's real GIS button stacked invisibly
 * on top of it, same size, opacity 0 -- a click lands on the real
 * button underneath ours, so the actual sign-in still goes through
 * Google Identity Services' own verified flow rather than us
 * reimplementing any part of it.
 */
export function GoogleButton({ onError }: { onError?: (message: string) => void }) {
  const { loginWithGoogle } = useAuth();
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!CLIENT_ID || !overlayRef.current) return;

    const scriptId = "google-identity-services";
    const render = () => {
      if (!window.google || !overlayRef.current) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: (resp: { credential: string }) => {
          loginWithGoogle(resp.credential).catch((err: unknown) => {
            onError?.(err instanceof ApiError ? err.message : "Google sign-in failed. Please try again.");
          });
        },
      });
      window.google.accounts.id.renderButton(overlayRef.current, {
        theme: "outline",
        size: "large",
        width: 320,
      });
    };

    if (document.getElementById(scriptId)) {
      render();
      return;
    }
    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = render;
    document.body.appendChild(script);
  }, [loginWithGoogle, onError]);

  if (!CLIENT_ID) {
    if (process.env.NODE_ENV !== "production") {
      // Silent in prod (a deployment may intentionally ship without Google
      // login), but this exact "nothing renders, no error anywhere" is
      // also what a missing env var looks like -- so surface it loudly
      // in dev/preview builds instead of leaving it to be diagnosed from
      // the outside.
      console.warn(
        "[GoogleButton] NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set — the Google " +
          "sign-in button will not render. Set it in frontend/.env.local " +
          "(see .env.local.example) and restart the dev server, or in your " +
          "host's environment variables and redeploy (NEXT_PUBLIC_* vars are " +
          "baked in at build time)."
      );
    }
    return null; // Google login not configured -- other methods still work.
  }

  return (
    <div className="relative w-full">
      <button
        type="button"
        tabIndex={-1}
        aria-hidden="true"
        className="group flex w-full items-center justify-center gap-2.5 rounded-xl border border-hairline bg-surface-raised px-4 py-2.5 text-sm font-medium text-ink transition-colors group-hover:border-ink/20 hover:bg-surface-overlay"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <path
            fill="#4285F4"
            d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.9C16.66 14.2 17.64 11.9 17.64 9.2Z"
          />
          <path
            fill="#34A853"
            d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.95v2.33A9 9 0 0 0 9 18Z"
          />
          <path
            fill="#FBBC05"
            d="M3.95 10.7A5.4 5.4 0 0 1 3.67 9c0-.59.1-1.17.28-1.7V4.97H.95A9 9 0 0 0 0 9c0 1.45.35 2.83.95 4.03l3-2.33Z"
          />
          <path
            fill="#EA4335"
            d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .95 4.97l3 2.33C4.66 5.17 6.65 3.58 9 3.58Z"
          />
        </svg>
        <span className="transition-transform group-active:scale-[0.98]">Continue with Google</span>
      </button>
      <div ref={overlayRef} className="absolute inset-0 overflow-hidden rounded-xl opacity-0 [&>div]:!w-full" />
    </div>
  );
}
