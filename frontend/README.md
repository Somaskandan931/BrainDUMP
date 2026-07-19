# Brain Dump

> Dump your thoughts. Let AI handle the rest.

Brain Dump is a local-first, AI-powered personal operating system designed for a single user.

Instead of manually organizing tasks, planning projects, estimating work, and managing schedules, Brain Dump automatically transforms unstructured thoughts into actionable plans.

It parses brain dumps into projects, breaks goals into roadmaps, estimates effort, schedules work, reprioritizes tasks, and replans automatically when priorities or deadlines change.

> Not a task manager you organize — one that organizes itself around you.

---

## Overview

Brain Dump is being developed incrementally in **9 milestones**, with each milestone representing a complete and reviewable layer of the system.

| Milestone | Description | Status |
|------------|-------------|--------|
| 1 | Architecture & Folder Structure | Complete |
| 2 | Database Schema & SQLAlchemy Models | Complete |
| 3 | FastAPI Backend & REST APIs | Complete |
| 4 | Ollama Integration & AI Agents | Complete |
| 5 | Scheduler & Planning Engine | Complete |
| 6 | Google Calendar Integration | Complete |
| 7 | Next.js Frontend | Complete |
| 8 | Analytics & Machine Learning | Complete |
| 9 | Testing, Docker & Deployment | In Progress |

For a complete explanation of the architecture, see `ARCHITECTURE.md`.

---

## Features

- Natural language brain dump processing
- Goal planning engine
- AI task decomposition
- Automatic scheduling
- Dynamic replanning
- Multi-agent AI pipeline
- Productivity analytics
- Weekly review generation
- Google Calendar integration
- Local Ollama inference
- Offline-first architecture

---

## Technology Stack

### Frontend

- Next.js
- React
- Tailwind CSS
- shadcn/ui
- Recharts

### Backend

- FastAPI
- SQLAlchemy
- SQLite
- APScheduler

### AI

- Ollama
- Qwen 3
- Sentence Transformers
- FAISS

### Integrations

- Google Calendar API

---

## Quick Start

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

Backend

```
http://localhost:8000
```

Swagger Documentation

```
http://localhost:8000/docs
```

Health Check

```
http://localhost:8000/health
```

---

### Optional Integrations

To enable Google Calendar synchronization:

1. Copy `.env.example` to `.env`
2. Follow the instructions in

```
backend/integrations/INTEGRATIONS.md
```

The application functions normally even without these integrations.

---

### Frontend

```bash
cd frontend

npm install

cp .env.local.example .env.local

npm run dev
```

Frontend

```
http://localhost:3000
```

---

## Current Functionality

The following modules are fully connected to the production backend.

- Dashboard
- Brain Dump
- Goal Engine
- Projects (CRUD)
- Tasks & Subtasks
- AI Chat
- Calendar
- Scheduler
- Morning Planning
- Nightly Replanning
- Google Calendar Sync
- Analytics Dashboard
- Weekly Review
- Productivity Metrics
- Machine Learning Retraining Pipeline

No mocked data is used.

---

## Documentation

| Document | Description |
|----------|-------------|
| `ARCHITECTURE.md` | Overall system architecture |
| `backend/api/API.md` | API reference |
| `frontend/FRONTEND.md` | Frontend architecture |
| `backend/ANALYTICS.md` | Analytics & ML pipeline |
| `backend/integrations/INTEGRATIONS.md` | Calendar setup |

---

## Design Principles

### Local First

Brain Dump uses SQLite and Ollama to keep AI inference local.

No user data leaves the machine except through the optional Google Calendar synchronization.

---

### Single User

Brain Dump is designed exclusively for personal productivity.

Authentication, teams, permissions, billing, and multi-tenancy are intentionally out of scope.

---

### Agent-Based Architecture

Brain Dump is built around independent AI agents rather than a single chatbot.

Each responsibility is isolated:

- Brain Dump Parser
- Goal Planner
- Task Breakdown
- Time Estimator
- Scheduler
- Priority Engine
- Reflection Agent

This modular design makes the system easier to extend, test, and maintain.

---

### AI Determines What Comes Next

The core UX principle is simple:

> The user should never need to ask, "What should I work on next?"

Brain Dump continuously evaluates deadlines, priorities, calendar availability, estimated effort, task dependencies, and historical productivity to determine the highest-value task at any moment.

---

### Graceful Integrations

Google Calendar sync is optional.

If it is unavailable or not configured, Brain Dump continues functioning normally while skipping only the affected synchronization step.

---

## Vision

Brain Dump is not intended to be another AI task manager.

It is a local-first AI operating system that understands goals, plans work, adapts to changing priorities, learns from productivity patterns, and continuously optimizes personal execution.