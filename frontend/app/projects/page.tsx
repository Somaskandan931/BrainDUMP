"use client";

import { FormEvent, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { useProjects } from "@/hooks/useProjects";
import { useTasks } from "@/hooks/useTasks";
import { FolderKanban } from "lucide-react";

function NewProjectForm({ onCreate, onCancel }: { onCreate: (name: string, description: string) => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    await onCreate(name.trim(), description.trim());
    setSaving(false);
  }

  return (
    <Card className="mb-4">
      <form onSubmit={handleSubmit}>
        <div className="flex items-center justify-between">
          <h3 className="font-display text-sm font-medium text-ink">New project</h3>
          <button type="button" onClick={onCancel} className="text-ink-faint hover:text-ink">
            <X size={16} />
          </button>
        </div>
        <div className="mt-3 flex flex-col gap-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
            className="w-full rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
          />
        </div>
        <div className="mt-3 flex justify-end">
          <Button type="submit" variant="primary" size="sm" disabled={!name.trim() || saving}>
            {saving ? "Creating…" : "Create project"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default function ProjectsPage() {
  const [showForm, setShowForm] = useState(false);
  const { projects, isLoading, create } = useProjects();
  const { tasks } = useTasks();

  const countsByProject = useMemo(() => {
    const map = new Map<number, number>();
    for (const t of tasks) {
      if (t.project_id == null) continue;
      map.set(t.project_id, (map.get(t.project_id) ?? 0) + 1);
    }
    return map;
  }, [tasks]);

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Projects</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Created by brain dumps and the goal engine, or added directly below.
        </p>
      </TopBar>

      <main className="flex-1 p-6 md:p-8">
        <div className="mb-4 flex justify-end">
          {!showForm && (
            <Button variant="primary" size="sm" onClick={() => setShowForm(true)}>
              <Plus size={14} /> New project
            </Button>
          )}
        </div>

        {showForm && (
          <NewProjectForm
            onCancel={() => setShowForm(false)}
            onCreate={async (name, description) => {
              await create({ name, description: description || null });
              setShowForm(false);
            }}
          />
        )}

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <EmptyState
            icon={<FolderKanban size={22} />}
            title="No projects yet"
            description="Brain-dump a few thoughts, describe a goal, or create one manually — projects are the parent for your tasks."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} taskCount={countsByProject.get(p.id) ?? 0} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
