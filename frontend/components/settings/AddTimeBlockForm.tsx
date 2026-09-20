"use client";

import { FormEvent, useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/format";
import { TimeBlockCategory, TimeBlockCreate } from "@/services/types";

const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
const PRESETS: { label: string; days: number[] }[] = [
  { label: "Every day", days: [0, 1, 2, 3, 4, 5, 6] },
  { label: "Weekdays", days: [0, 1, 2, 3, 4] },
  { label: "Weekends", days: [5, 6] },
];
const CATEGORIES: TimeBlockCategory[] = ["meal", "class", "gym", "other"];

export function AddTimeBlockForm({
  onAdd,
}: {
  onAdd: (payload: TimeBlockCreate) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [category, setCategory] = useState<TimeBlockCategory>("other");
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("08:30");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function toggleDay(d: number) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort()));
  }

  function reset() {
    setLabel("");
    setCategory("other");
    setStartTime("08:00");
    setEndTime("08:30");
    setDays([0, 1, 2, 3, 4, 5, 6]);
    setFormError(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!label.trim() || days.length === 0 || busy) return;
    if (endTime <= startTime) {
      setFormError("End time must be after start time.");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await onAdd({ label: label.trim(), category, start_time: startTime, end_time: endTime, days_of_week: days });
      reset();
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)} className="w-full">
        <Plus size={13} />
        Add time block
      </Button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-md border border-hairline bg-surface-raised p-3"
    >
      <Input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Breakfast, Gym, CS 101…"
        autoFocus
      />

      <div className="flex flex-wrap items-center gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCategory(c)}
            className={cn(
              "rounded-full border px-2.5 py-1 text-[11px] font-medium capitalize transition-colors",
              category === c
                ? "border-primary/30 bg-primary-dim text-primary-hover"
                : "border-hairline text-ink-muted hover:text-ink"
            )}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="tnum" />
        <span className="text-[12px] text-ink-faint">to</span>
        <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} className="tnum" />
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          {DAY_LABELS.map((d, i) => (
            <button
              key={i}
              type="button"
              onClick={() => toggleDay(i)}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-medium transition-colors",
                days.includes(i)
                  ? "border-primary/30 bg-primary-dim text-primary-hover"
                  : "border-hairline text-ink-faint hover:text-ink"
              )}
            >
              {d}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => setDays(p.days)}
              className="text-[11px] text-ink-faint underline decoration-dotted hover:text-ink"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {formError && <p className="text-[12px] text-critical">{formError}</p>}

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={busy || !label.trim()}>
          {busy ? "Adding…" : "Add block"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            reset();
            setOpen(false);
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
