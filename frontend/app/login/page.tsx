"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Mail, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { authApi } from "@/services/api";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { GithubButton } from "@/components/auth/GithubButton";
import { AuthCard, AuthDivider, AuthError } from "@/components/auth/AuthCard";
import { PasswordField } from "@/components/auth/PasswordField";
import { ApiError } from "@/services/types";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [unverified, setUnverified] = useState(false);
  const [resent, setResent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setUnverified(false);
    setResent(false);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        // 403 here only ever means EMAIL_VERIFICATION_REQUIRED and an
        // unclicked link (see api/v1/auth.py login) -- everything else
        // that can go wrong (bad password, deactivated) is 401/other.
        setUnverified(err.status === 403 && err.message.toLowerCase().includes("verify"));
      } else {
        setError("Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function resendVerification() {
    setResent(false);
    try {
      await authApi.resendVerificationEmail(email);
      setResent(true);
    } catch {
      // resend is best-effort UI sugar; the request endpoint itself
      // never reveals success/failure, so silently no-op here too.
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to your personal AI OS."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-ink transition-colors hover:text-primary">
            Create one
          </Link>
        </>
      }
    >
      <div className="space-y-2.5">
        <GoogleButton onError={setError} />
        <GithubButton />
      </div>

      <AuthDivider />

      <form onSubmit={onSubmit} className="space-y-3">
        <div className="relative">
          <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl border border-hairline bg-surface-raised py-2.5 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-primary/60 focus:ring-2 focus:ring-primary/20"
          />
        </div>

        <PasswordField
          value={password}
          onChange={setPassword}
          placeholder="Password"
          autoComplete="current-password"
        />

        <div className="flex justify-end">
          <Link
            href="/forgot-password"
            className="text-xs font-medium text-ink-muted transition-colors hover:text-primary"
          >
            Forgot password?
          </Link>
        </div>

        {error && <AuthError message={error} />}

        {unverified && (
          <div className="text-xs text-ink-muted">
            {resent ? (
              "If that account needs verifying, a new link is on its way."
            ) : (
              <>
                Didn&apos;t get the link?{" "}
                <button
                  type="button"
                  onClick={resendVerification}
                  className="font-medium text-primary underline underline-offset-4"
                >
                  Resend verification email
                </button>
              </>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:bg-primary-hover active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthCard>
  );
}
