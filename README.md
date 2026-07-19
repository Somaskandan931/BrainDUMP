<div align="center">

# BrainDUMP

**Dump your work. We'll build the plan. You'll finish what matters.**

*A local-first, AI-powered execution operating system for a single user.*

[![Status](https://img.shields.io/badge/status-active--development-yellow)](#why-braindump)
[![Python](https://img.shields.io/badge/backend-FastAPI-009688)](#technology-stack)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000)](#technology-stack)
[![AI](https://img.shields.io/badge/AI-Ollama%20%2F%20Qwen%203-8A2BE2)](#technology-stack)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

</div>

---

Most productivity apps are places you organize tasks. BrainDUMP is the opposite: you dump unstructured thoughts in, and it turns them into projects, roadmaps, estimates, schedules, and a daily plan — then keeps replanning as priorities and deadlines shift.

> **The core idea:** you should never have to ask *"what should I work on next?"* BrainDUMP already knows.

## Table of Contents

- [Why BrainDUMP](#why-braindump)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [Optional Integrations](#optional-integrations)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Design Principles](#design-principles)
- [License](#license)

## Why BrainDUMP

Planning is the actual bottleneck, not execution. Every day you burn cycles deciding what to work on first, whether a deadline is realistic, or what to do when something slips.

BrainDUMP removes that overhead by continuously evaluating your deadlines, priorities, calendar availability, effort estimates, task dependencies, and historical productivity — and surfacing the single highest-value task at any moment.

Everything runs **locally** through Ollama, so your data never has to leave your machine.

## Features

- Natural language brain dump processing
- Goal planning engine with automatic roadmap generation
- AI-driven task decomposition
- Automatic scheduling around real calendar availability
- Dynamic replanning when priorities or deadlines change
- Multi-agent AI pipeline (not a single chatbot)
- Productivity analytics and weekly review generation
- Google Calendar integration (optional)
- Local Ollama inference — offline-first by design

## Technology Stack

| Layer | Stack |
|---|---|
| **Frontend** | Next.js, React, Tailwind CSS, shadcn/ui, Recharts |
| **Backend** | FastAPI, SQLAlchemy, SQLite, APScheduler |
| **AI** | Ollama, Qwen 3, Sentence Transformers, FAISS |
| **Integrations** | Google Calendar API |

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) installed and running locally

### Backend

```bash
cd backend

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app:app --reload --app-dir ..
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

### Frontend

```bash
cd frontend

npm install
cp .env.local.example .env.local
npm run dev
```

Frontend runs at **http://localhost:3000**.

## Optional Integrations

Google Calendar synchronization is optional — BrainDUMP functions normally without it and simply skips the affected sync step if it isn't configured.

To enable it:

1. Copy `.env.example` to `.env`
2. Follow the setup steps in [`backend/integrations/INTEGRATIONS.md`](backend/integrations/INTEGRATIONS.md)

## Architecture

The AI Execution Coach is built around independent agents rather than one monolithic chatbot, so each responsibility stays isolated, testable, and easy to extend. Per the PRD, business logic (scheduling, deadlines, prioritization) is always deterministic — the LLM interprets natural language and generates estimates, but algorithms make the actual execution decisions.

- **Brain Dump Agent** — converts unstructured thoughts into projects, tasks, and deadlines
- **Goal Planner Agent** — breaks a goal into projects, tasks, and a schedule
- **Deadline Agent** — answers "can I finish before X?" with probability, risk, and required hours
- **Scheduler Agent** — rebuilds the schedule in response to natural-language changes
- **Replan Agent** — moves work and protects deadlines when plans are disrupted
- **Next Task Agent** — answers "what should I work on now?" with a single recommendation
- **Analytics Agent** — explains productivity patterns (completion history, estimation error, workload)

For the full system design, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Documentation

| Document | Description |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Overall system architecture |
| [`backend/api/API.md`](backend/api/API.md) | API reference |
| [`frontend/FRONTEND.md`](frontend/FRONTEND.md) | Frontend architecture |
| [`backend/ANALYTICS.md`](backend/ANALYTICS.md) | Analytics & ML pipeline |
| [`backend/integrations/INTEGRATIONS.md`](backend/integrations/INTEGRATIONS.md) | Calendar setup |

## Design Principles

Per the PRD, BrainDUMP's product philosophy rests on six principles:

1. **AI plans, humans execute.** Users should never spend significant time planning — BrainDUMP prioritizes, estimates, schedules, and adapts automatically.
2. **Every task needs a deadline.** Not a due date — a specific completion time, plus a latest safe start, risk score, and completion prediction.
3. **Plans must adapt.** Completing, delaying, skipping, or adding a task automatically updates the entire schedule.
4. **Capacity matters.** Scheduling accounts for available hours, meetings, workload, and recovery — not just raw time.
5. **Privacy first.** All AI runs locally by default, all data stays local, internet is optional, and cloud services (like Google Calendar) are integrations, not dependencies.
6. **Reduce cognitive load.** The product should reduce decisions, not create them — the answer to "what should I work on now?" should always be visible.

Team collaboration, shared workspaces, and multi-tenancy are explicitly out of scope for the MVP — BrainDUMP is built for a single user's personal execution.



---

<div align="center">

Not another AI task manager — a local-first operating system that understands your goals, plans your work, and adapts as things change.

</div>