"use client";

/**
 * GitHub redirects here with ?code=...&state=... after the user
 * approves (or ?error=... if they cancel). This page's only job is:
 * check `state` matches what GithubButton stashed (CSRF check), hand
 * `code` to the backend for the actual token exchange, then bounce to
 * the app or back to /login with an error to show.
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/services/types";

export default function GithubCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loginWithGithub } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const ghError = searchParams.get("error");
    const expectedState = sessionStorage.getItem("github_oauth_state");
    sessionStorage.removeItem("github_oauth_state");

    if (ghError) {
      setError("GitHub sign-in was cancelled.");
      return;
    }
    if (!code || !state || state !== expectedState) {
      setError("GitHub sign-in couldn't be verified. Please try again.");
      return;
    }

    loginWithGithub(code)
      .then(() => router.replace("/"))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "GitHub sign-in failed. Please try again.");
      });
    // Runs once on mount -- searchParams/router/loginWithGithub are all
    // stable for the lifetime of this one-shot callback page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-full w-full items-center justify-center bg-base p-6">
      <div className="w-full max-w-sm space-y-4 text-center">
        {error ? (
          <>
            <p className="text-sm text-critical">{error}</p>
            <button
              onClick={() => router.replace("/login")}
              className="text-sm font-medium text-primary underline underline-offset-4"
            >
              Back to sign in
            </button>
          </>
        ) : (
          <>
            <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-ink-faint border-t-primary" />
            <p className="text-sm text-ink-muted">Finishing sign-in…</p>
          </>
        )}
      </div>
    </div>
  );
}
