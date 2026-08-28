# Current To-Do List

This list is now tracked against the staged plan in `WEBSITE_DEVELOPMENT_PLAN.md`. Items below are immediate residual items from the plan's Stage 1 (verification) that did not get covered by the Stage 0 smoke test.

## Stage 10 — Launch Hardening (in progress, 2026-06-29)

Four sub-projects done this session (see CHANGELOG 2026-06-29 "later"–"later 4"). All flag-gated/additive so local dev is unchanged.

- [done] Self-contained bundle: share-link TTL + 410 enforcement + daily cleanup job; Google write-back retries + non-silent logging; CORS hardening.
- [done] Organizer auth (Supabase): backend was already complete; added flag-gated frontend auth (client, bearer injection, AuthProvider, RequireAuth on /create + /request/[id], /signin magic-link). **Live sign-in unverified — needs a Supabase project (`NEXT_PUBLIC_SUPABASE_*` + `SUPABASE_JWT_SECRET`) and `ALLOW_DEV_AUTH=false`.**
- [done] Twilio SMS behind `SMS_MODE=twilio`. **Live delivery unverified — needs `TWILIO_*` creds.**
- [done] Accessibility pass: axe-core audit in e2e; fixed the one serious contrast issue (`--accent`). Zero serious/critical violations on landing/create/signin/respond.
- [remaining] Lighthouse perf/SEO/best-practices pass (a11y category is covered). Google write-back retries + token-refresh job were partially addressed (retries added); a background token-refresh job is still open.

## Recently Resolved (do not re-add)

- Responder identity refactor: replaced contact_key matching with `resolve_participant` (logged-in user → invite token → email). Per-participant invite URLs, magic-respond on invited-email collisions, organizer-verification guards. See WEBSITE_DEVELOPMENT_PLAN.md "Identity-model refactor".

## Verification Pass 2026-06-29 (Stage 1) — defects found + fixed

Ran the full local stack (Postgres + Redis + uvicorn + Celery worker) and exercised every built feature. Four defects found; all fixed and verified. See CHANGELOG 2026-06-29.

- **[fixed] Celery worker registered zero tasks.** `app/workers/celery_app.py` declared `task_routes` for `app.workers.tasks.*` but never imported the module, so `@celery.task` never registered. The worker booted with an empty `[tasks]` list — reminder automation could only ever fire via the manual `/reminders/ping` endpoint. Fixed with `include=["app.workers.tasks"]`.
- **[fixed] No periodic schedule for the reminder sweep.** Even once registered, nothing invoked `enqueue_due_reminders` on a cadence (no `beat_schedule`, no `.delay()` callers). Added `beat_schedule` driving it every `REMINDER_SWEEP_INTERVAL_MINUTES` (default 15). **Requires running `celery ... beat` alongside the worker** — see CLAUDE.md.
- **[fixed] Playwright backend specs were CORS-blocked.** The e2e config boots the web dev server on port 3100, but backend CORS only allowed 3000, so every browser-side fetch failed with "Failed to fetch." Stage 9 only ever verified the skip-without-backend path, so these specs had never passed green. Added 3100 origins to the dev CORS default; all 4 specs now pass.
- **[fixed] db-backed tests errored instead of skipping without Postgres.** `tests/test_participant_resolution.py` had no skip guard despite the CHANGELOG claiming "6 db-backed tests skip cleanly." Added an `OperationalError` guard in `setUp`; suite now reports `OK (skipped=6)` with no DB.

### Still open

- **Google Calendar write-back with a real connected account is still unverified.** The graceful no-connection path is verified (finalize succeeds and emits ICS without a Google connection). Real write-back needs `GOOGLE_CLIENT_ID/SECRET` populated + a real OAuth connection (or a manually inserted `CalendarConnection`). Note: write-back failures are currently swallowed silently (`except Exception` in `scheduled_events.finalize_scheduled_event`) — Stage 10 owns retries/observability here.
- Decide whether reminder delivery should remain file-outbox-first in local/dev or move to a more production-like path (re-raise during Stage 4).

## Web App Polish

- Review copied share-link UX and make sure links open the attendee response page cleanly on mobile.
- Decide whether the organizer detail page needs a clearer post-confirmation success state beyond the current summary and ICS link.
- Add lightweight end-to-end coverage for the Next.js organizer and attendee flows once the local backend loop is stable.

## Product Direction

- Treat `calendar_syncing_app_web` as the active frontend and keep `calendar_syncing_app_frontend` as legacy reference only.
- Decide whether to archive the Flutter prototype from active development.
- Move next milestone work to Google Calendar read integration for organizer free/busy data.
- Plan the smarter slot generation milestone after the web-first loop is stable.

## Local Tooling

- `setup-local.ps1` (workspace root) provisions and launches the full stack in one command. It lives in the meta-folder, which is not a Git repo, so it is **not version-controlled** — back it up if it matters.
- **`docker-compose.yml` has no `beat` service.** `docker compose up --build` starts `api` + `worker` but never the scheduler, so the all-containers path still can't fire scheduled reminders or the daily share-link cleanup. `setup-local.ps1` sidesteps this by running beat on the host; the compose gap is unfixed.
- The dev database had accumulated ~14 expired share links that were never cleaned, confirming the daily `cleanup_expired_share_links` job has never actually run locally (beat was never running). Worth a sanity check once beat runs regularly.

## Nice To Have Later

- Set `allowedDevOrigins` in the web app's `next.config` to silence the Next.js cross-origin dev warning emitted when Playwright drives the dev server on port 3100 (currently just a warning; will be required in a future Next.js major).
- Add PWA installability after the core web loop proves useful.
- Add SMS reminder support.
- Add Outlook integration.
- Add a richer organizer account area once repeat usage is established.
