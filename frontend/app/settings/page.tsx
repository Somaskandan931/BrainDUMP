"use client";

import { ExternalLink, Moon } from "lucide-react";
import { useEffect, useState } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { TimeBlockRow } from "@/components/settings/TimeBlockRow";
import { AddTimeBlockForm } from "@/components/settings/AddTimeBlockForm";
import { DemoWorkspaceCard } from "@/components/settings/DemoWorkspaceCard";
import { useSettings, useTimeBlocks } from "@/hooks/useSettings";
import { useTheme } from "@/components/theme/ThemeProvider";
import { BASE_URL } from "@/services/api";
import { friendlyApiError } from "@/lib/format";

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

const HOURS = Array.from({ length: 24 }, (_, h) => h);

function formatHour(h: number): string {
  const period = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:00 ${period}`;
}

function HourSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (h: number) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink tnum focus:border-primary focus:outline-none"
    >
      {HOURS.map((h) => (
        <option key={h} value={h}>
          {formatHour(h)}
        </option>
      ))}
    </select>
  );
}

function ProfileSection() {
  const { settings, isLoading, error, refresh, update } = useSettings();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (settings) {
      setDisplayName(settings.display_name);
      setEmail(settings.email);
    }
  }, [settings]);

  return (
    <Card>
      <CardHeader eyebrow="You" title="Profile" />
      {isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : error ? (
        <ErrorState message={friendlyApiError(error, "Couldn't load settings.")} onRetry={() => refresh()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-ink-muted">Display name</span>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              onBlur={() => displayName !== settings?.display_name && update({ display_name: displayName })}
              placeholder="Your name"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-ink-muted">Email</span>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => email !== settings?.email && update({ email })}
              placeholder="you@example.com"
            />
          </label>
        </div>
      )}
    </Card>
  );
}

function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  const { settings, update } = useSettings();
  const [saving, setSaving] = useState(false);

  // Once real Settings load from the backend, let it decide the theme —
  // but only the first time this browser has no explicit local choice,
  // so a device the user already toggled never gets silently flipped
  // back by an older saved value.
  useEffect(() => {
    if (!settings) return;
    const hasLocalChoice = window.localStorage.getItem("bd-theme") !== null;
    if (!hasLocalChoice) setTheme(settings.dark_mode ? "dark" : "light");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  async function toggleDarkMode(checked: boolean) {
    setTheme(checked ? "dark" : "light");
    setSaving(true);
    await update({ dark_mode: checked });
    setSaving(false);
  }

  return (
    <Card>
      <CardHeader eyebrow="Look and feel" title="Appearance" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-raised text-ink-muted">
            <Moon size={14} />
          </span>
          <div>
            <p className="text-[13px] font-medium text-ink">Dark mode</p>
            <p className="text-[12px] text-ink-muted">Switch between light and dark theme</p>
          </div>
        </div>
        <Switch checked={theme === "dark"} onChange={toggleDarkMode} label="Dark mode" disabled={saving} />
      </div>
    </Card>
  );
}

function AvailableHoursSection() {
  const { settings, isLoading, error, refresh, update } = useSettings();

  if (isLoading) {
    return (
      <Card>
        <CardHeader eyebrow="When the scheduler can pack tasks in" title="Available Hours" />
        <Skeleton className="h-24 w-full" />
      </Card>
    );
  }
  if (error || !settings) {
    return (
      <Card>
        <CardHeader eyebrow="When the scheduler can pack tasks in" title="Available Hours" />
        <ErrorState message={friendlyApiError(error, "Couldn't load settings.")} onRetry={() => refresh()} />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader eyebrow="When the scheduler can pack tasks in" title="Available Hours" />
      <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
        <div>
          <p className="mb-2 text-[12px] font-medium uppercase tracking-[0.1em] text-ink-faint">Weekdays</p>
          <div className="flex items-center gap-2">
            <HourSelect
              value={settings.weekday_start_hour}
              onChange={(h) => update({ weekday_start_hour: h })}
            />
            <span className="text-[12px] text-ink-faint">–</span>
            <HourSelect value={settings.weekday_end_hour} onChange={(h) => update({ weekday_end_hour: h })} />
          </div>
        </div>
        <div>
          <p className="mb-2 text-[12px] font-medium uppercase tracking-[0.1em] text-ink-faint">Weekends</p>
          <div className="flex items-center gap-2">
            <HourSelect
              value={settings.weekend_start_hour}
              onChange={(h) => update({ weekend_start_hour: h })}
            />
            <span className="text-[12px] text-ink-faint">–</span>
            <HourSelect value={settings.weekend_end_hour} onChange={(h) => update({ weekend_end_hour: h })} />
          </div>
        </div>
      </div>
    </Card>
  );
}

function TimeBlocksSection() {
  const { timeBlocks, isLoading, error, refresh, create, remove } = useTimeBlocks();

  return (
    <Card>
      <CardHeader eyebrow="Protected time" title="Time Blocks" />
      <p className="mb-3 text-[13px] text-ink-muted">
        Block off time for meals, classes, gym, etc. The schedule works around these.
      </p>

      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : error ? (
        <ErrorState message={friendlyApiError(error, "Couldn't load time blocks.")} onRetry={() => refresh()} />
      ) : timeBlocks.length === 0 ? (
        <p className="mb-3 text-[12px] text-ink-faint">No time blocks yet.</p>
      ) : (
        <div className="mb-3 flex flex-col divide-y divide-hairline">
          {timeBlocks.map((b) => (
            <TimeBlockRow key={b.id} block={b} onDelete={remove} />
          ))}
        </div>
      )}

      <AddTimeBlockForm onAdd={create} />
    </Card>
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
        <ProfileSection />
        <AppearanceSection />
        <AvailableHoursSection />
        <TimeBlocksSection />
        <DemoWorkspaceCard />

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
          <p className="mb-2 text-[13px] text-ink-muted">
            Google Calendar syncs to whichever account completes OAuth consent
            (<code className="tnum text-ink">primary</code> calendar by default). To pin it to a
            specific calendar, set <code className="tnum text-ink">GOOGLE_CALENDAR_ID</code> in{" "}
            <code className="tnum text-ink">.env</code> — see the setup doc below.
          </p>
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
