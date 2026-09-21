"use client";

/**
 * Redirects the browser to GitHub's OAuth consent screen. The actual
 * token exchange happens server-side once GitHub redirects back to
 * /auth/github/callback with a `code` -- see that page and
 * backend/auth/github_login.py for why this can't be a client-side
 * popup+token flow the way Google's button is (GitHub never hands the
 * browser anything more than a one-time code; only the backend holds
 * the client secret needed to exchange it).
 *
 * `state` is a random value stashed in sessionStorage before the
 * redirect and checked against what GitHub sends back, the standard
 * OAuth CSRF mitigation -- without it, an attacker could trick a
 * victim's browser into completing *the attacker's* GitHub login on
 * the victim's session.
 */

const CLIENT_ID = process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID;
const REDIRECT_URI =
  process.env.NEXT_PUBLIC_GITHUB_REDIRECT_URI ??
  (typeof window !== "undefined" ? `${window.location.origin}/auth/github/callback` : "");

export function GithubButton({ label = "Continue with GitHub" }: { label?: string }) {
  if (!CLIENT_ID) {
    if (process.env.NODE_ENV !== "production") {
      // See the matching warning in GoogleButton.tsx -- same failure
      // mode: no button, no error, nothing to see unless you know to
      // check this specific env var.
      console.warn(
        "[GithubButton] NEXT_PUBLIC_GITHUB_CLIENT_ID is not set — the GitHub " +
          "sign-in button will not render. Set it in frontend/.env.local " +
          "(see .env.local.example) and restart the dev server, or in your " +
          "host's environment variables and redeploy (NEXT_PUBLIC_* vars are " +
          "baked in at build time)."
      );
    }
    return null; // GitHub login not configured -- other methods still work.
  }

  function handleClick() {
    const state = crypto.randomUUID();
    sessionStorage.setItem("github_oauth_state", state);

    const params = new URLSearchParams({
      client_id: CLIENT_ID as string,
      redirect_uri: REDIRECT_URI,
      scope: "read:user user:email",
      state,
    });
    window.location.href = `https://github.com/login/oauth/authorize?${params.toString()}`;
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="group flex w-full items-center justify-center gap-2.5 rounded-xl border border-hairline bg-surface-raised px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-ink/20 hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
        <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.29 9.4 7.86 10.93.57.1.78-.25.78-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.88-1.36-3.88-1.36-.52-1.34-1.28-1.7-1.28-1.7-1.04-.72.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.75 2.7 1.25 3.36.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14 0 1.55-.01 2.79-.01 3.17 0 .3.2.66.79.55A10.52 10.52 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
      </svg>
      <span className="transition-transform group-active:scale-[0.98]">{label}</span>
    </button>
  );
}
