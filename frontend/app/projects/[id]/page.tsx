"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ListChecks, Plus, Trash2 } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { TaskRow } from "@/components/tasks/TaskRow";
import { useProject, useProjects } from "@/hooks/useProjects";
import { useTasks } from "@/hooks/useTasks";
import { Importance } from "@/services/types";

const IMPORTANCE_OPTIONS: Importance[] = ["low", "medium", "high", "critical"];

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const router = useRouter();
  const { project, isLoading: projectLoading } = useProject(id);
  const { remove: removeProject } = useProjects();
  const { tasks, isLoading: tasksLoading, create, complete } = useTasks({ projectId: id });

  const [title, setTitle] = useState("");
  const [importance, setImportance] = useState<Importance>("medium");
  const [deadline, setDeadline] = useState("");
  const [adding, setAdding] = useState(false);

  async function handleAddTask(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setAdding(true);
    await create({
      project_id: id,
      title: title.trim(),
      importance,
      deadline: deadline ? new Date(deadline).toISOString() : null,
    });
    setTitle("");
    setDeadline("");
    setAdding(false);
  }

  const pending = tasks.filter((t) => t.status !== "completed" && t.status !== "cancelled");
  const done = tasks.filter((t) => t.status === "completed");

  return (
    <>
      <TopBar>
        <Link
          href="/projects"
          className="mb-1 inline-flex items-center gap-1 text-[12px] text-ink-faint hover:text-ink"
        >
          <ArrowLeft size={13} /> Projects
        </Link>
        {projectLoading ? (
          <Skeleton className="h-6 w-48" />
        ) : (
          <h1 className="font-display text-xl font-semibold text-ink">{project?.name}</h1>
        )}
      </TopBar>

      <main className="flex-1 p-6 md:p-8">
        {projectLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !project ? (
          <EmptyState title="Project not found" description="It may have been deleted." />
        ) : (
          <>
            <Card className="mb-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="mb-2 flex items-center gap-2">
                    <Badge tone={project.status === "active" ? "signal" : "neutral"}>
                      {project.status}
                    </Badge>
                    <span className="text-[11px] text-ink-faint">
                      {tasks.length} task{tasks.length === 1 ? "" : "s"} · {done.length} done
                    </span>
                  </div>
                  {project.description && (
                    <p className="text-[13px] text-ink-muted">{project.description}</p>
                  )}
                  {project.goal_text && (
                    <p className="mt-2 text-[12px] text-ink-faint">
                      Goal: <span className="text-ink-muted">{project.goal_text}</span>
                    </p>
                  )}
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={async () => {
                    if (!confirm(`Delete "${project.name}" and all its tasks?`)) return;
                    await removeProject(project.id);
                    router.push("/projects");
                  }}
                >
                  <Trash2 size={13} /> Delete
                </Button>
              </div>
            </Card>

            <Card className="mb-4">
              <CardHeader eyebrow="POST /api/tasks" title="Add a task" />
              <form onSubmit={handleAddTask} className="flex flex-col gap-2 sm:flex-row">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Task title"
                  className="min-w-0 flex-1 rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
                />
                <select
                  value={importance}
                  onChange={(e) => setImportance(e.target.value as Importance)}
                  className="rounded-md border border-hairline bg-surface-raised px-2 py-2 text-[13px] text-ink focus:border-primary focus:outline-none"
                >
                  {IMPORTANCE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="rounded-md border border-hairline bg-surface-raised px-2 py-2 text-[13px] text-ink focus:border-primary focus:outline-none"
                />
                <Button type="submit" variant="primary" size="sm" disabled={!title.trim() || adding}>
                  <Plus size={14} /> Add
                </Button>
              </form>
            </Card>

            <Card>
              <CardHeader eyebrow="Live from /api/tasks" title="Tasks" />
              {tasksLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : tasks.length === 0 ? (
                <EmptyState icon={<ListChecks size={20} />} title="No tasks in this project yet" />
              ) : (
                <div className="flex flex-col divide-y divide-hairline">
                  {[...pending, ...done].map((t) => (
                    <TaskRow key={t.id} task={t} onComplete={(taskId) => complete(taskId)} />
                  ))}
                </div>
              )}
            </Card>
          </>
        )}
      </main>
    </>
  );
}
