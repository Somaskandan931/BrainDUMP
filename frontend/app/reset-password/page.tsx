"use client";

/**
 * Landed on from the link in email_service.send_password_reset_email:
 * /reset-password?token=<jwt>. The token is purpose-scoped and expires
 * in config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES (30 min by default) --
 * see api/v1/auth.py's /password-reset/confirm.
 */

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import { authApi } from "@/services/api";
import { AuthCard, AuthError } from "@/components/auth/AuthCard";
import { PasswordField } from "@/components/auth/PasswordField";
import { ApiError } from "@/services/types";

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const token = searchParams?.get("token") ?? null;

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Those passwords don't match.");
      return;
    }
    if (!token) {
      setError("This reset link is missing its token. Request a new one.");
      return;
    }

    setSubmitting(true);
    try {
      await authApi.confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthCard
        title="Reset your password"
        subtitle="This link looks incomplete."
        footer={
          <Link href="/forgot-password" className="font-medium text-ink transition-colors hover:text-primary">
            Request a new link
          </Link>
        }
      >
        <AuthError message="No reset token was found in this link. Copy the full link from your email, or request a new one." />
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard
        title="Password reset"
        subtitle="You're all set."
        footer={
          <Link href="/login" className="font-medium text-ink transition-colors hover:text-primary">
            Sign in
          </Link>
        }
      >
        <div className="flex items-start gap-2.5 rounded-lg border border-primary/25 bg-primary/10 px-3 py-3 text-sm text-ink">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span>Your password has been changed. Sign in with your new password.</span>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="Make it something you haven't used here before."
      footer={
        <Link href="/login" className="font-medium text-ink transition-colors hover:text-primary">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} className="space-y-3">
        <PasswordField
          value={password}
          onChange={setPassword}
          placeholder="New password (8+ characters)"
          minLength={8}
          autoComplete="new-password"
        />
        <PasswordField
          value={confirmPassword}
          onChange={setConfirmPassword}
          placeholder="Confirm new password"
          minLength={8}
          autoComplete="new-password"
        />

        {error && <AuthError message={error} />}

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:bg-primary-hover active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {submitting ? "Resetting…" : "Reset password"}
        </button>
      </form>
    </AuthCard>
  );
}
