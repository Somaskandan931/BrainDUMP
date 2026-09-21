# Brain Dump — start here

This folder is the complete project: backend, frontend, tests and deploy config, with the
multi-user auth refactor finished. `CHANGES.md` lists every file that changed;
`AUTH_REFACTOR_STATUS.md` explains the bugs that were found and what is still open.

## Before you put this over an existing copy

1. **Back up `data/tasks.db`** if it holds anything you care about. Upgrading assigns every
   existing row to an inactive placeholder account (`legacy@local`) that nobody can log into,
   so old data becomes invisible. Fine for throwaway dev data; if it matters, it needs a
   "claim legacy data" step that doesn't exist yet.
2. Your `.env` is not in this package and is left alone.
3. Delete the old Todoist files if you're copying files over an existing tree instead of
   replacing the folder: `backend/api/todoist.py`, `backend/integrations/todoist.py`,
   `backend/schemas/todoist.py`, `backend/services/todoist_sync_service.py`.

## Run it locally

Backend (from this folder):

```bash
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
echo 'JWT_SECRET_KEY=paste-a-long-random-string-here' >> .env     # required
uvicorn backend.app.main:app --reload                               # http://localhost:8000
```

The database is created/upgraded automatically on startup. The AI features expect an
`OPENROUTER_API_KEY` in `.env` (free tier available at https://openrouter.ai/keys);
everything else works without it.

Frontend:

```bash
cd frontend
npm install
cp .env.local.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                            # http://localhost:3000
```

Register an account on the login page. Each account only ever sees its own data.

Tests: `python -m pytest` (161 tests).

## Optional settings (`.env`)

| Variable | What it does |
|---|---|
| `JWT_SECRET_KEY` | **Required.** Signs login tokens. Without it the app uses an insecure dev default. |
| `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REDIRECT_URI`, `FRONTEND_URL` | Turns on per-user Google Calendar sync (Settings -> Connect Google Calendar). Setup steps: `backend/integrations/INTEGRATIONS.md`. |
| `INTEGRATION_ENCRYPTION_KEY` | Encrypts each user's stored Google token. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GOOGLE_LOGIN_CLIENT_ID` (+ `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on the frontend) | "Sign in with Google". |
| `AUTH_LOGIN_MAX_FAILURES`, `AUTH_LOGIN_IP_MAX_FAILURES`, `AUTH_REGISTER_MAX_PER_IP` | Login/register rate limits (defaults: 5 / 20 / 10). |

## Deploying

`DEPLOY.md` (Render + Netlify with Ollama) or `DEPLOY-FREE.md`
(free tier, OpenRouter) at the repo root.

## Not verified here

- The real Google OAuth consent flow (the tests fake Google) — needs your own OAuth client and
  one manual pass.
- `next build` (the sandbox couldn't reach Google Fonts); `tsc` and `next lint` pass.
