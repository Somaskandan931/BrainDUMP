"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useAuth } from "@/lib/auth";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { ApiError } from "@/services/types";

export default function RegisterPage() {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password, name || undefined);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-base p-6">
      <div className="w-full max-w-sm space-y-6 rounded-xl border border-ink/10 bg-surface p-8 shadow-sm">
        <div className="space-y-1 text-center">
          <h1 className="font-display text-xl font-semibold text-ink">Brain Dump</h1>
          <p className="text-sm text-ink/60">Create your account.</p>
        </div>

        <GoogleButton onError={setError} />

        <div className="flex items-center gap-3 text-xs uppercase text-ink/40">
          <div className="h-px flex-1 bg-ink/10" />
          or
          <div className="h-px flex-1 bg-ink/10" />
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-ink/15 bg-base px-3 py-2 text-sm outline-none focus:border-ink/40"
          />
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-ink/15 bg-base px-3 py-2 text-sm outline-none focus:border-ink/40"
          />
          <input
            type="password"
            required
            minLength={8}
            placeholder="Password (8+ characters)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-ink/15 bg-base px-3 py-2 text-sm outline-none focus:border-ink/40"
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-ink px-3 py-2 text-sm font-medium text-base disabled:opacity-50"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-center text-sm text-ink/60">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-ink underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
