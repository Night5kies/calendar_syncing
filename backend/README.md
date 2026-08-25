# Backend Local Setup

The backend is a FastAPI service backed by Postgres and Redis.

## Local development defaults

The settings layer now supports a local-first mode:

- `ENV=local`
- `USE_LOCAL_DATABASE_IN_DEV=true`
- `LOCAL_DATABASE_URL=postgresql+psycopg://app:app@127.0.0.1:5432/app`
- `USE_LOCAL_REDIS_IN_DEV=true`
- `LOCAL_REDIS_URL=redis://127.0.0.1:6379/0`

When those flags are enabled, local runs use the local Postgres and Redis URLs even if `DATABASE_URL` or `REDIS_URL` in `.env` point at remote infrastructure.

## One-time setup

1. Copy `.env.example` to `.env` if you do not already have one.
2. Keep `ENV=local`, `USE_LOCAL_DATABASE_IN_DEV=true`, and `USE_LOCAL_REDIS_IN_DEV=true` for normal local work.
3. Start Postgres and Redis:

```powershell
docker compose up -d db redis
```

4. Apply migrations:

```powershell
alembic upgrade head
```

## Run the API, worker, and beat

Host-run, one process per terminal:

```powershell
uvicorn app.main:app --reload
```

```powershell
celery -A app.workers.celery_app.celery worker --loglevel=INFO
```

```powershell
celery -A app.workers.celery_app.celery beat --loglevel=INFO
```

The worker only *consumes* tasks. **`beat` is what enqueues the periodic
`enqueue_due_reminders` sweep** (every `REMINDER_SWEEP_INTERVAL_MINUTES`,
default 15) and the daily expired-share-link cleanup. Without a running `beat`,
reminders only go out via the manual `POST /v1/requests/{id}/reminders/ping`
endpoint.

On worker boot, check that it registers four tasks (`send_request_reminders`,
`enqueue_due_reminders`, `cleanup_expired_share_links`,
`send_confirmation_invites`). A worker that starts with an empty `[tasks]` list
means the `include=[...]` wiring in `app/workers/celery_app.py` regressed.

Docker Compose:

```powershell
docker compose up --build
```

The compose services override `LOCAL_DATABASE_URL` and `LOCAL_REDIS_URL` so the API and worker use the container service names instead of `127.0.0.1`.

## Local auth

Organizer routes support a dev-auth fallback in local mode:

- `ALLOW_DEV_AUTH=true`
- `DEV_USER_ID=11111111-1111-1111-1111-111111111111`
- `DEV_USER_EMAIL=local-organizer@syzy.dev`

That lets the web app call organizer endpoints locally without wiring real auth first.

## Tests

### Unit tests

The suite uses the stdlib `unittest` framework (there is no pytest config):

```powershell
python -m unittest discover -s tests                                    # all tests
python -m unittest tests.test_meeting_requests                          # one module
python -m unittest tests.test_meeting_requests.MeetingRequestTests.test_status_transitions
```

Expect **63 tests**, all passing with Postgres up.

Without Postgres the 11 db-backed tests skip cleanly rather than erroring
(`Ran 63 tests ... OK (skipped=11)`), so this suite is safe to run before
`docker compose up`. The skips are 6 in `tests/test_participant_resolution.py`
plus 5 in `tests/test_share_links.py`; both guard on `OperationalError` in
`setUp`. If you see errors instead of skips there, Postgres is down *and* a skip
guard regressed.

### End-to-end smoke

With the API running, exercise the full organizer -> share -> reminder ->
attendee response -> finalize loop:

```powershell
python scripts/test_reminder_flow.py
```

If local dev auth is disabled, pass a bearer token with `--bearer-token`.

### Outbox inspection

`NOTIFICATION_MODE=file` (the default) writes emails as JSON to
`NOTIFICATION_OUTBOX_DIR` (default `dev_outbox/`) instead of sending them. SMS
always writes to the outbox unless `SMS_MODE=twilio`. After a smoke run, eyeball
`dev_outbox/` — you should see 3 reminders plus a confirmation email carrying
the ICS attachment. For anything reminder- or invite-shaped, this is the check
that the *right* thing was queued, not just that the call returned 200.

## Full local test sequence

### The scripted path

`setup-local.ps1` in the workspace root does everything below in one command —
prerequisites, Docker daemon, containers, dependencies, migrations, the test
suite, then launches the api, worker, beat, and web dev server in separate
windows and health-checks them:

```powershell
# from the workspace root (one level up)
.\setup-local.ps1
.\setup-local.ps1 -NoLaunch    # provision only
.\setup-local.ps1 -FullTest    # also run the Playwright suite
```

It is idempotent — re-running skips anything already up. Note it lives in the
workspace meta-folder, which is not a Git repo, so it is not version-controlled
with this project.

### The manual path

Start to finish, assuming Docker Desktop is already running:

```powershell
# from calendar_syncing_app_backend/
docker compose up -d db redis
alembic upgrade head
python -m unittest discover -s tests

# then, in separate terminals
uvicorn app.main:app --reload
celery -A app.workers.celery_app.celery worker --loglevel=INFO
celery -A app.workers.celery_app.celery beat --loglevel=INFO

# back in the first terminal, once the API is up
python scripts/test_reminder_flow.py
```

The web app's Playwright suite runs against this same backend on port 8000 — see
`../calendar_syncing_app_web/README.md`.

Not covered by any of the above: real Supabase auth and real Google Calendar
write-back. Both are flag-gated off locally and need credentials to exercise.
