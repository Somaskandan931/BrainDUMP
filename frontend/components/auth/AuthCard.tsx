import { ReactNode } from "react";

/**
 * Shared shell for /login and /register: the soft ambient glow behind
 * the card, the mark + heading block, and the card surface itself.
 * Split out once both pages needed the identical treatment -- keeps
 * the actual forms (which do differ) the only thing each page owns.
 */
export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden bg-base p-6">
      {/* Ambient glow -- two soft, low-opacity radial blooms in the
          palette's own primary/signal hues, not a generic template
          gradient. Purely decorative: aria-hidden, fixed, never
          intercepts clicks. */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[-10%] h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-primary/20 blur-[120px]" />
        <div className="absolute bottom-[-15%] right-[10%] h-[380px] w-[380px] rounded-full bg-signal/10 blur-[120px]" />
      </div>

      <div className="relative w-full max-w-sm animate-fade-up space-y-8">
        <div className="flex flex-col items-center space-y-4 text-center">
          <Mark />
          <div className="space-y-1.5">
            <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">{title}</h1>
            <p className="text-sm text-ink-muted">{subtitle}</p>
          </div>
        </div>

        <div className="rounded-2xl border border-hairline bg-surface/80 p-7 shadow-[0_1px_0_0_rgba(255,255,255,0.02)_inset,0_20px_60px_-15px_rgba(0,0,0,0.5)] backdrop-blur-xl">
          {children}
        </div>

        <p className="text-center text-sm text-ink-muted">{footer}</p>
      </div>
    </div>
  );
}

/** Small geometric mark -- a rounded square with a signal-colored pulse
    dot, echoing the "instrument panel" idea at a glance without needing
    an actual logo asset. */
function Mark() {
  return (
    <div className="relative flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary-hover shadow-lg shadow-primary/30">
      <span className="h-2 w-2 rounded-full bg-signal shadow-[0_0_8px_2px] shadow-signal/70" />
    </div>
  );
}

export function AuthDivider() {
  return (
    <div className="my-6 flex items-center gap-3">
      <div className="h-px flex-1 bg-hairline" />
      <span className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">or continue with email</span>
      <div className="h-px flex-1 bg-hairline" />
    </div>
  );
}

export function AuthError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-critical/25 bg-critical-dim px-3 py-2.5 text-sm text-critical">
      <svg viewBox="0 0 20 20" fill="currentColor" className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true">
        <path
          fillRule="evenodd"
          d="M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Zm-7-4a1 1 0 1 0-2 0v4a1 1 0 0 0 2 0V6Zm-1 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clipRule="evenodd"
        />
      </svg>
      <span>{message}</span>
    </div>
  );
}
