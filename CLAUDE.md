# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

This is the parent repository for three Git submodules:

- `backend/` — FastAPI + Postgres + Redis + Celery service. Active.
- `web/` — Next.js 15 / React 19 web frontend. **Active launch surface.**
- `app/` — Legacy Flutter native app prototype. **Reference only**, driven by mock data, not the launch frontend. Do not extend this unless the user explicitly asks.

Top-level docs (`Social Calendar App PRD.txt`, `EXECUTION_ROADMAP.md`, `CHANGELOG.md`, `ToDos.md`) describe the product: SYZY, a link-first social scheduling tool. Organizer creates a request in the web app, shares a tokenized link in chat, attendees respond on mobile web without an account, organizer confirms a winner, backend writes the event back to Google Calendar and emits ICS.

Each subproject remains an independent repository. Run child-repository Git commands from the relevant submodule directory; run parent-repository Git commands from this directory.

## Backend (`backend/`)

FastAPI app mounted at `/v1`, plus `/health` and `/db-check`. Entry point: `app/main.py`.

### Local development

The settings layer has a **local-first override** in `app/core/config.py`: when `ENV=local` and `USE_LOCAL_DATABASE_IN_DEV=true` / `USE_LOCAL_REDIS_IN_DEV=true`, `LOCAL_DATABASE_URL` and `LOCAL_REDIS_URL` win over `DATABASE_URL` / `REDIS_URL`. This is intentional so that a `.env` pointing at remote Supabase does not leak into local runs. When debugging "why is local talking to the remote DB", check those flags first.

One-time setup:

```powershell
# from backend/
cp .env.example .env                # if no .env yet; keep ENV=local
docker compose up -d db redis
alembic upgrade head
```

Run API + worker on the host:

```powershell
uvicorn app.main:app --reload
celery -A app.workers.celery_app.celery worker --loglevel=INFO
celery -A app.workers.celery_app.celery beat --loglevel=INFO
```

The worker only consumes tasks; **`beat` is what enqueues the periodic `enqueue_due_reminders` sweep** (every `REMINDER_SWEEP_INTERVAL_MINUTES`, default 15). Without a running `beat`, reminders only go out via the manual `POST /v1/requests/{id}/reminders/ping` endpoint. Note `app/workers/celery_app.py` must list the tasks module under `include=[...]` for `@celery.task`s to register — a worker that boots with an empty `[tasks]` list means that wiring regressed.

Run everything in containers:

```powershell
docker compose up --build
```

Compose overrides `LOCAL_DATABASE_URL` / `LOCAL_REDIS_URL` to point at the `db` / `redis` service names instead of `127.0.0.1`, so the same `.env` works both host-run and in-container.

### Tests

Backend tests use the stdlib `unittest` framework (no pytest config file present):

```powershell
python -m unittest discover -s tests          # all tests
python -m unittest tests.test_meeting_requests # single module
python -m unittest tests.test_meeting_requests.MeetingRequestTests.test_status_transitions
```

End-to-end smoke against a running local API (organizer → share → attendee response → reminder → finalize):

```powershell
python scripts/test_reminder_flow.py
# pass --bearer-token if ALLOW_DEV_AUTH is off
```

### Auth model

Routes use `get_current_user` (`app/api/deps.py`), which expects a Supabase-signed bearer token. In local mode, if no token is present **and** `ALLOW_DEV_AUTH=true`, the dependency returns a synthetic `CurrentUser(user_id=DEV_USER_ID, email=DEV_USER_EMAIL)`. This is what lets the Next.js dev server hit organizer endpoints without real auth. If you are debugging "401 in dev", confirm `ENV=local` and `ALLOW_DEV_AUTH=true`.

Public share endpoints (`/v1/share/public/{token}`, `/v1/share/public/{token}/responses`) intentionally do not require auth — attendees respond with a `guest_key` instead.

### Backend architecture

- `app/api/v1/` — route modules mounted by `router.py`: `auth` (`/me`), `requests` (`/requests/...`), `share` (`/share/...`), `calendar`.
- `app/services/` — business logic. `meeting_requests.py` owns the state machine (`next_status_on_response`, `validate_manual_proposal_rules`, `dispatch_request_reminders`) and reminder dispatch. `scheduled_events.py` finalizes a winning proposal into a `ScheduledEvent`. `confirmation_artifacts.py` builds ICS. `notifications.py` sends email/SMS. `calendar.py` handles connections and free/busy.
- `app/workers/` — Celery worker. `tasks.send_request_reminders` (per-request) and `tasks.enqueue_due_reminders` (cron-like sweep) both call `dispatch_request_reminders`.
- `app/providers/google.py` — Google Calendar provider (read free/busy, write event back).
- `app/models/` — SQLAlchemy 2.0 models. The state machine lives across `MeetingRequest` (status), `Participant`, `Proposal`, `ProposalResponse`, `ShareLink`, `ScheduledEvent`, `ReminderLog`.
- `app/db/session.py` — engine bound to `settings.effective_database_url`.
- `alembic/versions/` — migrations are linear and named by feature (`phase_one_tables`, `request_status_responses_and_availability`, `poll_proposals_schema`, `calendar_cache_and_shares`, `request_reminders`, `confirmation_artifacts`).

### Notifications

`NOTIFICATION_MODE=file` (default) writes emails as JSON to `NOTIFICATION_OUTBOX_DIR` (default `dev_outbox/`) instead of sending. Set `NOTIFICATION_MODE=smtp` plus `SMTP_*` vars to actually deliver. SMS always writes to the outbox in this codebase. When verifying reminder flow locally, inspect `dev_outbox/` rather than expecting real email.

## Web App (`web/`)

Next.js 15 App Router, React 19, TypeScript strict. No styling framework — just `app/globals.css`.

```powershell
# from web/
npm install
npm run dev          # http://localhost:3000
npm run build
npm start
```

Backend base URL comes from `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000` (`lib/api.ts`). The backend's CORS allowlist already includes `localhost:3000`, `127.0.0.1:3000`, and the e2e port `:3100`.

### Organizer auth

Auth is **flag-gated** (`lib/supabase.ts:isAuthEnabled`). With `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` **unset** (local dev default), the web app runs with no sign-in and the backend dev-auth fallback (`ENV=local` + `ALLOW_DEV_AUTH=true`) handles organizer requests — this is what the e2e suite relies on. Set **both** vars to enable real auth: `AuthProvider` tracks the Supabase session, `lib/api.ts` attaches `Authorization: Bearer <token>`, and `RequireAuth` (wired via `app/create/layout.tsx` + `app/request/[id]/layout.tsx`) redirects unauthenticated organizers to `/signin` (magic-link). Attendee pages stay public — never gate `/events/[id]/respond` or `/respond/[token]`. The backend already verifies these tokens (`app/core/security.py:decode_supabase_token`, HS256 via `SUPABASE_JWT_SECRET`) and enforces `organizer_id` ownership on every `/requests/{id}` route. Production must run with `ALLOW_DEV_AUTH=false`.

### Routes

- `/` — landing (`app/page.tsx`)
- `/signin` — organizer magic-link sign-in (only meaningful when auth is enabled)
- `/create` — organizer create-request flow (auth-gated)
- `/request/[id]` — organizer detail / progress / finalize (auth-gated)
- `/respond/[id]` — attendee response page hit via shared link (public)

`lib/api.ts` is the single source of truth for backend contracts — the `OrganizerRequestDetail` and `PublicSharePayload` types mirror what `/v1/requests/{id}` and `/v1/share/public/{token}` return. When changing a backend payload, update both ends in the same change.

There are no automated frontend tests yet (`ToDos.md` calls this out as a planned addition).

## Legacy Flutter App (`app/`)

Kept for UI/design reference. Driven by mock data, not wired to the backend. Per the project's own README and roadmap, do not add features here unless the user explicitly returns to a native-client strategy. If asked to make a frontend change without qualification, assume `web/` is the target.

## Product Conventions Worth Knowing

- **Proposals lock after a request leaves `draft`** (`can_edit_proposals` / `validate_manual_proposal_rules`). To change times after send, the flow is cancel + recreate. Do not add edit paths that bypass this without an explicit product decision.
- **Manual proposals are capped at `MAX_MANUAL_PROPOSALS = 5`** in the MVP.
- **Reminders are capped at `MAX_REMINDERS_PER_PARTICIPANT = 3`** as anti-spam.
- **Attendees never have accounts.** They are identified by `guest_key` plus optional email/phone, and matched server-side by email → phone → guest_key fallback.
- **Privacy default is free/busy, never event titles.** Any new calendar-read feature should preserve this.
