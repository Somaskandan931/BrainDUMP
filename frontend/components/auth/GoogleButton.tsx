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
 */
export function GoogleButton({ onError }: { onError?: (message: string) => void }) {
  const { loginWithGoogle } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!CLIENT_ID || !containerRef.current) return;

    const scriptId = "google-identity-services";
    const render = () => {
      if (!window.google || !containerRef.current) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: (resp: { credential: string }) => {
          loginWithGoogle(resp.credential).catch((err: unknown) => {
            onError?.(err instanceof ApiError ? err.message : "Google sign-in failed. Please try again.");
          });
        },
      });
      window.google.accounts.id.renderButton(containerRef.current, {
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
    return null; // Google login not configured -- email/password still works.
  }

  return <div ref={containerRef} />;
}
