"use client";

import { FormEvent, useRef, useState } from "react";
import { Bot, Send, User } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { chatApi } from "@/services/api";
import { ApiError } from "@/services/types";
import { cn } from "@/lib/format";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  agent?: string;
}

let nextId = 1;

/**
 * The AI Execution Coach (PRD §24) — a router in front of specialized,
 * data-grounded agents (Next Task, Replan, Deadline, Brain Dump), not a
 * general chatbot. Every message hits POST /api/chat, which picks the
 * right agent via services/ai_coach_service.py; open-ended questions
 * fall through to a constrained LLM that's still grounded in real
 * task/risk data and refuses off-topic chat. Quick actions below just
 * pre-fill the canonical phrasing each agent matches on.
 */
export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId++,
      role: "assistant",
      text: "Ask me about your plan — \"what's next\", \"can I finish X by Friday\", \"replan my week\" — or use the quick actions below.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function push(role: Message["role"], text: string, agent?: string) {
    setMessages((m) => [...m, { id: nextId++, role, text, agent }]);
    requestAnimationFrame(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight));
  }

  async function send(text: string) {
    push("user", text);
    setBusy(true);
    try {
      const res = await chatApi.send(text);
      push("assistant", res.message, res.agent);
    } catch (err) {
      push(
        "assistant",
        err instanceof ApiError
          ? err.status === 0
            ? "Couldn't reach the backend."
            : err.message
          : "Something went wrong answering that."
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    await send(text);
  }

  const quickReplan = () => !busy && send("Replan my week");
  const quickNextTask = () => !busy && send("What should I do next?");

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">AI Coach</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Routes to the Next Task, Replan, Deadline, and Brain Dump agents — grounded in your real tasks, not a general chatbot.
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
                  {m.agent && (
                    <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.1em] text-ink-faint">
                      {m.agent.replace(/_/g, " ")}
                    </div>
                  )}
                  {m.text}
                </div>
              </div>
            ))}
            {busy && <p className="pl-9 text-[12px] text-ink-faint">Thinking…</p>}
          </div>

          <form onSubmit={handleSubmit} className="flex gap-2 border-t border-hairline p-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Can I finish this by Friday? What should I do next?"
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
