"use client";

/**
 * Landed on from the link in email_service.send_verification_email:
 * /verify-email?token=<jwt>. Auto-confirms on mount -- there's no form,
 * just a link to click, so the useful thing to show is the outcome.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import { authApi } from "@/services/api";
import { AuthCard, AuthError } from "@/components/auth/AuthCard";
import { ApiError } from "@/services/types";

type Status = "checking" | "success" | "error";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const token = searchParams?.get("token") ?? null;
  const pending = searchParams?.get("pending") === "1";
  const pendingEmail = searchParams?.get("email") ?? "";

  const [status, setStatus] = useState<Status>("checking");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pending) {
      setStatus("checking");
      return;
    }
    if (!token) {
      setStatus("error");
      setError("No verification token was found in this link. Copy the full link from your email.");
      return;
    }
    authApi
      .confirmEmail(token)
      .then(() => setStatus("success"))
      .catch((err: unknown) => {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      });
    // One-shot on mount, same as the GitHub OAuth callback page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, token]);

  return (
    <AuthCard
      title="Verify your email"
      subtitle={pending ? "One last step before you can sign in." : status === "checking" ? "Just a moment…" : ""}
      footer={
        <Link href="/login" className="font-medium text-ink transition-colors hover:text-primary">
          Back to sign in
        </Link>
      }
    >
      {pending && (
        <div className="space-y-2 rounded-lg border border-primary/25 bg-primary/10 px-3 py-3 text-sm text-ink">
          <div className="flex items-start gap-2.5">
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>
              We sent a verification link{pendingEmail ? <> to <strong>{pendingEmail}</strong></> : ""}.
              Open that email and click the link to activate your account.
            </span>
          </div>
        </div>
      )}

      {!pending && status === "checking" && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Confirming your email…
        </div>
      )}

      {status === "success" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-primary/25 bg-primary/10 px-3 py-3 text-sm text-ink">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span>Your email is verified. You can sign in now.</span>
        </div>
      )}

      {status === "error" && error && <AuthError message={error} />}
    </AuthCard>
  );
}
