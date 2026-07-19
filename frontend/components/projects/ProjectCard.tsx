"use client";

import Link from "next/link";
import { Project } from "@/services/types";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { timeAgo } from "@/lib/format";

const STATUS_TONE = {
  active: "signal",
  completed: "primary",
  archived: "neutral",
} as const;

export function ProjectCard({ project, taskCount }: { project: Project; taskCount?: number }) {
  return (
    <Link href={`/projects/${project.id}`}>
      <Card className="h-full transition-colors hover:border-primary/40">
        <div className="mb-2 flex items-start justify-between gap-2">
          <h3 className="font-display text-[15px] font-medium text-ink">{project.name}</h3>
          <Badge tone={STATUS_TONE[project.status]}>{project.status}</Badge>
        </div>
        {project.description && (
          <p className="mb-3 line-clamp-2 text-[13px] text-ink-muted">{project.description}</p>
        )}
        <div className="flex items-center justify-between text-[11px] text-ink-faint">
          <span>{taskCount != null ? `${taskCount} task${taskCount === 1 ? "" : "s"}` : ""}</span>
          <span>updated {timeAgo(project.updated_at)}</span>
        </div>
      </Card>
    </Link>
  );
}
