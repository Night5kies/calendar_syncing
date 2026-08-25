# SYZY Web App

Next.js 15 (App Router) + React 19 + TypeScript strict. This is the **active
launch frontend** for SYZY — the link-first social scheduling tool. The Flutter
app in `../calendar_syncing_app_frontend/` is legacy reference only.

No styling framework; all styles live in `app/globals.css`.

## Setup

```powershell
npm install
npm run dev          # http://localhost:3000
```

The backend base URL comes from `NEXT_PUBLIC_API_BASE_URL`, defaulting to
`http://127.0.0.1:8000` (see `lib/api.ts`). The backend's CORS allowlist already
includes `localhost:3000`, `127.0.0.1:3000`, and the e2e port `:3100`.

Most pages need the backend running — see
`../calendar_syncing_app_backend/README.md`.

## Routes

- `/` — landing
- `/signin` — organizer magic-link sign-in (only meaningful when auth is enabled)
- `/create` — organizer create-request flow (auth-gated)
- `/request/[id]` — organizer detail / progress / finalize (auth-gated)
- `/events/[id]/respond` — attendee response page (public)
- `/respond/[id]` — legacy share URL, redirects to `/events/[id]/respond` (public)
- `/settings/availability` — weekly hours, one-off blocks, Google Calendar connect

## Organizer auth

Auth is **flag-gated** via `lib/supabase.ts:isAuthEnabled`, which is true only
when both `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set.

With both **unset** (the local dev default), the app runs with no sign-in and the
backend's dev-auth fallback (`ENV=local` + `ALLOW_DEV_AUTH=true`) handles
organizer requests. This is the mode the e2e suite relies on.

Set both to enable real auth: `AuthProvider` tracks the Supabase session,
`lib/api.ts` attaches `Authorization: Bearer <token>`, and `RequireAuth`
redirects unauthenticated organizers to `/signin`. Attendee pages stay public —
never gate `/events/[id]/respond` or `/respond/[id]`.

## Tests

### Type check and build

```powershell
npx tsc --noEmit
npm run build
```

### Playwright e2e

First time only — downloads the Chromium build:

```powershell
npm run test:e2e:install
```

Then, **with the backend running on port 8000**:

```powershell
npm run test:e2e       # headless
npm run test:e2e:ui    # Playwright UI mode
```

Playwright boots its own Next.js dev server on port 3100 automatically — do not
start `npm run dev` yourself first.

The suite is **10 specs**: 1 landing smoke, 3 organizer-flow, 2 auth, 4
accessibility.

- Backend **up**: 10 passed.
- Backend **down**: 6 passed, 4 skipped.

Four specs are backend-dependent — the 3 in `organizer-flow.spec.ts` plus the
attendee-respond case in `a11y.spec.ts`, since that page needs a seeded event.
They probe `GET /health` first and `test.skip` with a clear reason, so the suite
stays green when only the web app changed. That also means **a green run is not
proof the backend paths were exercised** — check the output for skips.

The accessibility specs (`tests-e2e/a11y.spec.ts`) run `@axe-core/playwright`
against the landing, create, signin, and attendee-respond pages and fail on any
serious or critical violation. Keep them at zero. Note the attendee-respond page
is only actually audited when the backend is running.

Env knobs: `E2E_PORT` (default `3100`), `E2E_BASE_URL`, `E2E_API_BASE_URL`
(default `http://127.0.0.1:8000`), `CI=1`. More detail in
`tests-e2e/README.md`.

## Full local test sequence

### The scripted path

`setup-local.ps1` in the workspace root brings up the whole stack — backend,
worker, beat, and this dev server — in one command, then health-checks it:

```powershell
# from the workspace root (two levels up from here)
.\setup-local.ps1
.\setup-local.ps1 -FullTest    # also runs the Playwright suite
```

It is idempotent, and skips any process already listening on its port. Note it
lives in the workspace meta-folder, which is not a Git repo, so it is not
version-controlled with this project.

### The manual path

With the backend, worker, and beat already running (see the backend README):

```powershell
npm install
npx tsc --noEmit
npm run build
npm run test:e2e
```

Not covered: real Supabase auth (the e2e suite deliberately runs in dev-auth
mode with `NEXT_PUBLIC_SUPABASE_*` unset) and real Google Calendar write-back.
Both need credentials.

## Backend contracts

`lib/api.ts` is the single source of truth for backend contracts — the
`OrganizerRequestDetail` and `PublicSharePayload` types mirror what
`/v1/requests/{id}` and `/v1/share/public/{token}` return. When changing a
backend payload, update both ends in the same change.
