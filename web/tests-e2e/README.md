# Playwright e2e suite

Smoke + regression coverage for the organizer + attendee flow, driven against a
running local backend (`http://127.0.0.1:8000` by default) and a Next.js dev
server that Playwright boots automatically on port 3100.

## First-time setup

```powershell
# from calendar_syncing_app_web/
npm install
npm run test:e2e:install   # downloads the Chromium build Playwright uses
```

## Running

Start the backend first (so the attendee + finalize specs don't skip):

```powershell
# from calendar_syncing_app_backend/
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload
```

Then from `calendar_syncing_app_web/`:

```powershell
npm run test:e2e            # headless run
npm run test:e2e:ui         # Playwright UI mode
```

The `landing.spec.ts` smoke runs without the backend. The
`organizer-flow.spec.ts` specs check `/health` first and skip with a clear
message if the backend isn't reachable, so the suite stays green when only the
web app changed.

## Env knobs

- `E2E_PORT` — dev server port (default `3100`)
- `E2E_BASE_URL` — full base URL override
- `E2E_API_BASE_URL` — backend base URL (default `http://127.0.0.1:8000`)
- `CI=1` — fails fast, fails on `test.only`, runs `--retries=1`
