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

## Run the API and worker

Host-run:

```powershell
uvicorn app.main:app --reload
```

```powershell
celery -A app.workers.celery_app.celery worker --loglevel=INFO
```

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

## Smoke test

After the API is running, you can exercise the organizer -> share -> attendee -> reminder -> finalize loop with:

```powershell
python scripts/test_reminder_flow.py
```

If local dev auth is disabled, pass a bearer token with `--bearer-token`.
