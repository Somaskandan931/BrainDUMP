import { Trash2, Utensils, GraduationCap, Dumbbell, Clock3 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { TimeBlock, TimeBlockCategory } from "@/services/types";

const CATEGORY_ICON: Record<TimeBlockCategory, typeof Utensils> = {
  meal: Utensils,
  class: GraduationCap,
  gym: Dumbbell,
  other: Clock3,
};

const CATEGORY_LABEL: Record<TimeBlockCategory, string> = {
  meal: "Meal",
  class: "Class",
  gym: "Gym",
  other: "Other",
};

const DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function daysLabel(days: number[]): string {
  const sorted = [...days].sort();
  if (sorted.length === 7) return "Every day";
  if (sorted.length === 5 && sorted.every((d, i) => d === i)) return "Weekdays";
  if (sorted.length === 2 && sorted[0] === 5 && sorted[1] === 6) return "Weekends";
  return sorted.map((d) => DAY_ABBR[d]).join(", ");
}

function to12h(hhmm: string): string {
  const parts = hhmm.split(":").map(Number);
  const h = parts[0] ?? 0;
  const m = parts[1] ?? 0;
  const period = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return m === 0 ? `${hour12}${period}` : `${hour12}:${String(m).padStart(2, "0")}${period}`;
}

export function TimeBlockRow({ block, onDelete }: { block: TimeBlock; onDelete: (id: string) => void }) {
  const Icon = CATEGORY_ICON[block.category];

  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-raised text-ink-muted">
          <Icon size={14} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-ink">{block.label}</p>
          <p className="text-[11px] text-ink-faint">
            <span className="tnum">
              {to12h(block.start_time)}–{to12h(block.end_time)}
            </span>
            {" · "}
            {daysLabel(block.days_of_week)}
            {" · "}
            {CATEGORY_LABEL[block.category]}
          </p>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(block.id)}
        aria-label={`Remove ${block.label}`}
        className="shrink-0 !px-2"
      >
        <Trash2 size={13} />
      </Button>
    </div>
  );
}
