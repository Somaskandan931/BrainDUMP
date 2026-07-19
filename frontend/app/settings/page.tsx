"use client";

import { ExternalLink } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { BASE_URL } from "@/services/api";

function DocLink({ href, label }: { href: string; label: string }) {
  return (
    <li>
      <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted">
        <ExternalLink size={12} className="text-ink-faint" />
        {label} — <code className="tnum text-ink-faint">{href}</code>
      </span>
    </li>
  );
}

export default function SettingsPage() {
  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Settings</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Brain Dump is local-first — most configuration lives in files, not this page.
        </p>
      </TopBar>

      <main className="flex-1 space-y-4 p-6 md:p-8">
        <Card>
          <CardHeader eyebrow="Frontend" title="Backend connection" />
          <p className="text-[13px] text-ink-muted">
            This app talks to <code className="tnum text-ink">{BASE_URL}</code>, read from{" "}
            <code className="tnum text-ink">NEXT_PUBLIC_API_URL</code> at build/run time. Change
            it in <code className="tnum text-ink">frontend/.env.local</code> (copy from{" "}
            <code className="tnum text-ink">.env.local.example</code>) and restart{" "}
            <code className="tnum text-ink">npm run dev</code>.
          </p>
        </Card>

        <Card>
          <CardHeader eyebrow="Backend" title="Local AI (Ollama)" />
          <p className="mb-2 text-[13px] text-ink-muted">
            Model and host are set server-side in <code className="tnum text-ink">backend/config.py</code>{" "}
            (<code className="tnum text-ink">OLLAMA_HOST</code>,{" "}
            <code className="tnum text-ink">OLLAMA_MODEL</code>) — there&apos;s no live-fetch of that
            value here on purpose, so this page never shows a config that could drift from the
            file that actually controls it.
          </p>
        </Card>

        <Card>
          <CardHeader eyebrow="Setup" title="Integrations" />
          <ul className="flex flex-col gap-2">
            <DocLink href="backend/integrations/INTEGRATIONS.md" label="Google Calendar setup" />
            <DocLink href="backend/ai/AGENTS.md" label="AI agent prompts and design" />
            <DocLink href="backend/services/PLANNING.md" label="Scheduler and priority engine" />
            <DocLink href="backend/api/API.md" label="Full API route table" />
          </ul>
        </Card>
      </main>
    </>
  );
}
