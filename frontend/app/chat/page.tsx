"use client";

import { FormEvent, useRef, useState } from "react";
import { Bot, Send, User } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { plannerApi } from "@/services/api";
import { ApiError } from "@/services/types";
import { cn } from "@/lib/format";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
}

let nextId = 1;

/**
 * There is no /api/chat route — the AI layer is a pipeline of
 * single-purpose agents (backend/ai/AGENTS.md), not a general chatbot.
 * This page is an honest front end for the two conversational entry
 * points that do exist: every message you type runs through the
 * brain-dump agent, and "Replan my week" / "What's next" call the real
 * scheduler endpoints directly. It says what it's doing, not "thinking…".
 */
export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId++,
      role: "assistant",
      text: "Tell me what's on your mind — I'll run it through the brain-dump agent and turn it into projects and tasks. Or use the quick actions below.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function push(role: Message["role"], text: string) {
    setMessages((m) => [...m, { id: nextId++, role, text }]);
    requestAnimationFrame(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    push("user", text);
    setInput("");
    setBusy(true);
    try {
      const res = await plannerApi.brainDump(text);
      if (res.projects.length === 0 && res.tasks.length === 0) {
        push("assistant", "Parsed that, but didn't extract any projects or tasks from it.");
      } else {
        const parts: string[] = [];
        if (res.projects.length)
          parts.push(`${res.projects.length} project${res.projects.length === 1 ? "" : "s"}: ${res.projects.map((p) => p.name).join(", ")}`);
        if (res.tasks.length)
          parts.push(`${res.tasks.length} task${res.tasks.length === 1 ? "" : "s"}: ${res.tasks.map((t) => t.title).join(", ")}`);
        push("assistant", `Created ${parts.join(" · ")}.`);
      }
    } catch (err) {
      push(
        "assistant",
        err instanceof ApiError
          ? `Couldn't parse that: ${err.message}`
          : "Couldn't reach the backend."
      );
    } finally {
      setBusy(false);
    }
  }

  async function quickReplan() {
    setBusy(true);
    push("user", "Replan my week");
    try {
      const res = await plannerApi.replan();
      push(
        "assistant",
        `Rescheduled ${res.rescheduled_count} task${res.rescheduled_count === 1 ? "" : "s"}. ` +
          `${res.demoted_tasks.length} demoted, ${res.at_risk_tasks.length} still at risk.`
      );
    } catch (err) {
      push("assistant", err instanceof ApiError ? err.message : "Replan failed.");
    } finally {
      setBusy(false);
    }
  }

  async function quickNextTask() {
    setBusy(true);
    push("user", "What should I do next?");
    try {
      const res = await plannerApi.nextTask();
      push(
        "assistant",
        res.task
          ? `${res.task.title} — ${res.task.importance} importance${res.task.estimated_hours ? `, ~${res.task.estimated_hours}h` : ""}.`
          : "Nothing queued right now."
      );
    } catch (err) {
      push("assistant", err instanceof ApiError ? err.message : "Couldn't fetch next task.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">AI Chat</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          A front end for the brain-dump, replan, and next-task agents — not a general chatbot.
        </p>
      </TopBar>

      <main className="flex flex-1 flex-col gap-3 p-6 md:p-8">
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={quickReplan} disabled={busy}>
            Replan my week
          </Button>
          <Button variant="secondary" size="sm" onClick={quickNextTask} disabled={busy}>
            What&apos;s next?
          </Button>
        </div>

        <Card className="flex flex-1 flex-col p-0">
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-5">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}
              >
                <div
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                    m.role === "user" ? "bg-primary-dim text-primary-hover" : "bg-surface-raised text-ink-muted"
                  )}
                >
                  {m.role === "user" ? <User size={13} /> : <Bot size={13} />}
                </div>
                <div
                  className={cn(
                    "max-w-[75%] rounded-md px-3 py-2 text-[13px]",
                    m.role === "user" ? "bg-primary-dim text-ink" : "bg-surface-raised text-ink-muted"
                  )}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {busy && <p className="pl-9 text-[12px] text-ink-faint">Working…</p>}
          </div>

          <form onSubmit={handleSubmit} className="flex gap-2 border-t border-hairline p-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Need internship report, gym tomorrow, interview next Friday…"
              className="flex-1 rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
            />
            <Button type="submit" variant="primary" size="sm" disabled={!input.trim() || busy}>
              <Send size={13} />
            </Button>
          </form>
        </Card>
      </main>
    </>
  );
}
