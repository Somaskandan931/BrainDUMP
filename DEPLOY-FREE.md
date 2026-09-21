# Deploying Brain Dump for $0 — fully hosted, nothing local required

AI now runs on **OpenRouter's hosted free tier** instead of a local Ollama
daemon (see `backend/ai/ollama_client.py`). That removes the one piece
that used to require your own machine — no terminal, no tunnel, no
"is my laptop on" dependency. Everything below runs on Render + Netlify.

## What "free" buys you now

| Piece | Free option | The catch |
|---|---|---|
| Frontend | Netlify free tier | None — fine long-term. |
| Backend (FastAPI) | Render free web service | Sleeps after 15 min idle (30-60s cold start on wake); 512MB RAM is tight once `sentence-transformers`/`faiss-cpu` load at boot. |
| AI (LLM) | OpenRouter free model | Rate-limited (free models cap requests/day), and free models are smaller/slower than qwen3:8b — good enough for this app's structured JSON tasks, but watch `backend/ai/prompts.py` output quality once it's live. |
| Database (SQLite) | Render's ephemeral disk | Not persistent — wiped on every redeploy. Free plan has no mountable disk. |
| Scheduler (7am/11pm jobs) | In-process on the free web service | Won't fire reliably while asleep — needs the keep-alive trick below. |

## 1. Get a free OpenRouter API key

1. Sign up at [openrouter.ai](https://openrouter.ai) (free, no card).
2. [openrouter.ai/keys](https://openrouter.ai/keys) → create a key.
3. Keep it handy for step 3 — you'll paste it into Render as a secret env
   var, never into the repo.

## 2. Push the repo

```bash
cd your-repo
git init
git add .
git commit -m "brain dump — deploy setup"
git branch -M main
git remote add origin https://github.com/<you>/brain-dump.git
git push -u origin main
```

## 3. Backend — Render, free plan

1. Render dashboard → New → Web Service → connect your repo.
2. Runtime: Docker, Dockerfile path `backend/Dockerfile`, context: repo root.
3. Instance type: **Free**.
4. Environment variables (or use `render.free.yaml` as a Blueprint):
   - `ALLOWED_ORIGINS` = your Netlify URL (fill in after step 4)
   - `OPENROUTER_API_KEY` = the key from step 1 — mark it **Secret** in Render's env var UI
   - `OPENROUTER_MODEL` = `meta-llama/llama-3.1-8b-instruct:free` (or any other `:free` slug from [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0))
   - `JWT_SECRET_KEY` = a long random string (Render can generate it)
   - `INTEGRATION_ENCRYPTION_KEY` = a Fernet key (command in `.env.example`) — **Secret**
   - `FRONTEND_URL` = your Netlify URL
   - `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET` / `GOOGLE_CALENDAR_REDIRECT_URI` = a Google **Web application** OAuth client and its callback, `https://<your-backend>.onrender.com/api/calendar/google/callback` (optional — omit to leave Calendar sync off)
   - `GOOGLE_LOGIN_CLIENT_ID` = for "Sign in with Google" (optional; also set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on Netlify)
   - `GOOGLE_CALENDAR_ID` = `primary`
5. Nothing to upload: each user connects their own Google account from the app.
6. Deploy. No CLI needed — this is all dashboard clicks.

**RAM note:** if the service crash-loops on boot, `sentence-transformers`/`faiss-cpu` importing at startup is almost certainly why — 512MB is tight. Say the word and I'll make those imports lazy (only load when an endpoint that needs them is actually called) to fit the free tier.

## 4. Frontend — Netlify, free plan

```bash
cd frontend
npm install
npm run build   # sanity-check locally first
```

Netlify dashboard → Import project → base directory `frontend` → env var
`NEXT_PUBLIC_API_URL` = your Render URL. Deploy, then copy the resulting
`https://<site>.netlify.app` back into Render's `ALLOWED_ORIGINS` and
redeploy the backend.

## 5. Keep the free backend awake for the scheduler

Free Render sleeps after 15 min idle, which would silently kill the
7am/11pm APScheduler jobs. Fix it for free with an external pinger:

- [cron-job.org](https://cron-job.org) (free, no card) → hit
  `https://your-backend.onrender.com/health` every 10 minutes.

This keeps it awake continuously, which is close to Render's 750 free
instance-hours/month ceiling (~730 hours = 24/7) — right at the edge but
within it.

## 6. If losing SQLite data on every redeploy is a dealbreaker

Swap SQLite for a free external Postgres that doesn't expire (Render's
own free Postgres expires after 30 days — Neon and Supabase's free tiers
don't). `backend/app/core/config.py` already reads `DATABASE_URL` from
the environment (falling back to the default SQLite path when unset),
and `psycopg[binary]` is already in `requirements.txt` — just set
`DATABASE_URL` to your Postgres connection string as a Render env var.

## Bottom line

$0/month, nothing running on your own machine, no terminal required once
it's deployed. The two remaining trade-offs are both free-tier physics,
not architecture problems: the backend cold-starts if the keep-alive
pinger ever lapses, and the free OpenRouter model is smaller/slower than
a self-hosted 8B model. If either becomes a real problem, the cheapest
upgrade is Render's $7/mo Starter plan for the backend (always-on) —
OpenRouter itself can stay free either way, or you can move to a paid
OpenRouter model per-request if free-tier rate limits become the
bottleneck.
