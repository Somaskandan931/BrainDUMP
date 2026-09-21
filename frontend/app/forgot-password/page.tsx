"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Mail, Loader2, CheckCircle2 } from "lucide-react";
import { authApi } from "@/services/api";
import { AuthCard, AuthError } from "@/components/auth/AuthCard";
import { ApiError } from "@/services/types";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // The backend always returns the same generic message whether or
      // not the email is registered, so there's nothing to branch on
      // here -- just show it.
      await authApi.requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="We'll email you a link to get back in."
      footer={
        <>
          Remembered it after all?{" "}
          <Link href="/login" className="font-medium text-ink transition-colors hover:text-primary">
            Back to sign in
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-primary/25 bg-primary/10 px-3 py-3 text-sm text-ink">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span>
            If an account exists for <strong>{email}</strong>, a reset link is on its way. It expires in 30
            minutes.
          </span>
        </div>
      ) : (
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

          {error && <AuthError message={error} />}

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:bg-primary-hover active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
