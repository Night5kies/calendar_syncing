# Change Log

## 2026-06-29 (later 4)

### Stage 10 (sub-project 4) — Accessibility pass
Automated the accessibility audit with `@axe-core/playwright` rather than eyeballing markup. New `tests-e2e/a11y.spec.ts` runs axe against the landing, create, signin, and attendee-respond pages and fails on any serious/critical violation.

- The audit surfaced a single serious issue repeated across pages: the primary CTA color `--accent: #d95d39` with white text measured **3.76:1**, below the WCAG AA 4.5:1 minimum (affected `.button-primary`, the active mode-toggle, and the create-submit button). Darkened `--accent` to `#c0492a` (and matched `--accent-soft`), which clears AA with margin. One token change resolved every flagged node.
- Result: all four pages report **zero serious/critical** axe violations.

### Verification
- Web: `npx tsc --noEmit` clean; `npx playwright test` → 10 passed (landing, 3 organizer-flow, 2 auth, 4 a11y).

This completes all four Stage 10 sub-projects selected for this pass (self-contained hardening, organizer auth, Twilio SMS, accessibility). Remaining Stage 10 items (Lighthouse perf/SEO beyond a11y) and live verification of auth/SMS/Google write-back are gated on external credentials.

## 2026-06-29 (later 3)

### Stage 10 (sub-project 3) — Real SMS provider (Twilio), flag-gated
SMS previously always wrote to the file outbox. Added a live Twilio path behind an `SMS_MODE` flag, mirroring the existing SMTP pattern.

- Settings: `SMS_MODE` (default `file`), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- `app/services/notifications.py`: `send_notification(channel="sms")` routes to `_send_sms_via_twilio` when `SMS_MODE=twilio`, else the outbox. New pure `build_twilio_payload` (URL + form data + basic-auth) keeps the request shape unit-testable; the sender posts via httpx (already a dependency — no new SDK). Unconfigured-but-enabled returns `failed: twilio_not_configured`; an HTTP ≥400 returns `failed: twilio_http_<code>`.
- 4 tests (`tests/test_notifications_sms.py`): payload builder, file-mode outbox, twilio configured (httpx.post mocked → sent), twilio unconfigured → failed.

**Activation (deferred — needs creds):** set `SMS_MODE=twilio` + the three `TWILIO_*` values. Live delivery is unverified without a Twilio account.

## 2026-06-29 (later 2)

### Stage 10 (sub-project 2) — Organizer auth (Supabase), flag-gated
Audit found the backend auth was already complete — `decode_supabase_token` verifies Supabase HS256 JWTs, `get_current_user` falls back to dev-auth only when `ENV=local` + `ALLOW_DEV_AUTH`, and `organizer_id` ownership is enforced on every `/requests/{id}` route. The entire gap was the **frontend**, which had no auth at all. Built as an additive, flag-gated layer so local/dev is unchanged.

- **`lib/supabase.ts`** — `isAuthEnabled` is true only when both `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set. Otherwise no client is created and the app runs against backend dev-auth (the e2e suite's mode).
- **`lib/api.ts`** — `request()` now attaches `Authorization: Bearer <token>` from the active Supabase session (no-op when auth is disabled).
- **`AuthProvider` + `useAuth`** — tracks the session via `onAuthStateChange`; exposes `signInWithEmail` (magic link via `signInWithOtp`) and `signOut`. Wraps the app in `app/layout.tsx`.
- **`RequireAuth`** — gates organizer pages, wired through new `app/create/layout.tsx` and `app/request/[id]/layout.tsx`. Renders children directly when auth is disabled; redirects to `/signin` when enabled and signed out. Attendee pages stay public.
- **`/signin`** — magic-link form; shows "Auth is not configured" in dev mode.
- Backend: 3 regression tests (`tests/test_auth_deps.py`) lock that dev-auth applies only in local mode with the flag on, and that a production env always requires real credentials.

**Activation (deferred — needs creds):** set the two `NEXT_PUBLIC_SUPABASE_*` vars (see web `.env.example`), point `SUPABASE_JWT_SECRET` at the project's JWT secret, and run the backend with `ALLOW_DEV_AUTH=false`. The live sign-in round-trip is unverified until a Supabase project is provided; default sign-in is magic link (Google OAuth is a small `signInWithOAuth` addition later).

### Verification
- Backend: 59 unit tests pass (+3 auth deps).
- Web: `npx tsc --noEmit` clean; `npm run build` succeeds (`/signin` route added); `npx playwright test` → 6 passed (+2 dev-mode auth specs confirming `/create` stays reachable and `/signin` reports auth-off).

## 2026-06-29 (later)

### Stage 10 (sub-project 1) — Self-contained launch hardening
First of four Stage 10 workstreams. No external accounts required; built test-first.

- **Share-link TTL + expiry enforcement.** `ShareLink.expires_at` existed but was never populated or checked, so links never expired. Added `SHARE_LINK_TTL_DAYS` (default 30), set `expires_at` on creation, and a new `app/services/share_links.py` with `compute_expires_at` / `is_share_link_expired`. The public share endpoints (`GET /v1/share/public/{token}`, `POST .../responses`) now go through `load_active_share_link`, which returns **410 Gone** for an expired token (legacy null-expiry rows stay valid forever, so existing links keep working).
- **Expired-link cleanup job.** New `delete_expired_share_links` service + `cleanup_expired_share_links` Celery task, wired into `beat_schedule` to run daily. Prevents unbounded `share_links` growth (the primary copied URL is the event URL, so token rows otherwise just accumulate).
- **Google write-back retries + silent-failure fix.** `finalize_scheduled_event` previously swallowed every write-back exception with a bare `except Exception: pass` — an organizer never learned the event failed to land on their calendar. Added a generic, injectable `app/services/retry.py:retry_call` (3 attempts, linear backoff) around the write-back, and replaced the silent except with a `logger.warning(..., exc_info=True)`. Write-back stays best-effort: the ICS artifact and confirmed status are unaffected on failure.
- **CORS/cookies hardening.** Replaced `allow_methods=["*"] / allow_headers=["*"]` (incompatible with `allow_credentials=True` under the CORS spec) with explicit allowlists: methods `GET/POST/PATCH/DELETE/OPTIONS`, headers `Authorization/Content-Type`.
- **Frontend.** `lib/api.ts` now extracts FastAPI's `{"detail": ...}` from error bodies (cleaner messages app-wide instead of raw JSON), and the legacy `/respond/[token]` page shows "This link has expired" on a 410.

### Verification
- Backend: `python -m unittest discover -s tests` → 56 pass (was 44; +9 share-link, +3 retry). Includes RED-proof that the expired-link 410 test fails without the enforcement branch.
- End-to-end: smoke passes; a freshly created share link now carries `expires_at` ~30 days out.
- Web: `npx tsc --noEmit` clean; `npx playwright test` → 4 passed.

## 2026-06-29

### Stage 1 — Verification of Built Features (+ 4 defect fixes)
Brought up the full local stack (Postgres + Redis via Docker, uvicorn, Celery worker) and exercised every built feature end to end. The smoke flow (`scripts/test_reminder_flow.py`) passed: create → share → manual ping (2 reminders) → attendee response via invite token → second ping (1 reminder, responder skipped) → finalize → ICS artifact. Outbox inspection confirmed 3 reminders + 1 confirmation email carrying the ICS attachment (Stage 8). Four defects surfaced and were fixed:

- **Celery worker registered zero tasks.** `app/workers/celery_app.py` configured `task_routes` for `app.workers.tasks.*` but never imported the module, so the `@celery.task` decorators never ran. The worker booted with an empty `[tasks]` list, meaning the scheduled reminder path was dead — reminders only ever went out via the synchronous `/reminders/ping` endpoint. Fixed by adding `include=["app.workers.tasks"]` to the `Celery()` constructor; the worker now registers `enqueue_due_reminders`, `send_request_reminders`, and `send_confirmation_invites`.
- **No periodic trigger for the reminder sweep.** There was no `beat_schedule` and no `.delay()`/`.apply_async()` caller anywhere, so `enqueue_due_reminders` would never run on a cadence even once registered. Added `celery.conf.beat_schedule` running it every `REMINDER_SWEEP_INTERVAL_MINUTES` (new setting, default 15). Requires a `celery beat` process — documented in CLAUDE.md and `.env.example`. Verified the selection logic directly: a request with a deadline inside the 6h window is picked up; a fresh request with a far deadline is not.
- **Playwright backend-dependent specs were CORS-blocked.** `playwright.config.ts` boots the Next.js dev server on port 3100, but the backend CORS allowlist only included port 3000, so all browser-side fetches failed with "Failed to fetch." Stage 9 had only ever verified the skip-without-backend path, so `organizer-flow.spec.ts` had never actually passed against a live backend. Added `http://localhost:3100` / `http://127.0.0.1:3100` to the dev CORS default. All 4 e2e specs now pass (attendee respond view, post-finalize confirmed view + Google/Outlook deep-links, organizer confirmed-event panel).
- **db-backed tests errored instead of skipping without Postgres.** `tests/test_participant_resolution.py` opened a session in `setUp` with no guard, so the 6 db-backed tests hard-errored when Postgres was down — contradicting the CHANGELOG's repeated "skip cleanly without local Postgres" claim (no skip guard existed anywhere in `tests/`). Added an `OperationalError` guard; the suite now reports `OK (skipped=6)` with no DB and 44 passing with DB up.

### Verification
- Backend: `python -m unittest discover -s tests` → 44 pass with Postgres up; 6 skip cleanly without it.
- End-to-end: `scripts/test_reminder_flow.py` passes against local uvicorn.
- Celery: worker boots and registers all 3 tasks; beat schedule resolves to the registered sweep task.
- Web: `npx playwright test` → 4 passed (was 1 passed / 3 failed before the CORS fix).
- Still open: real Google write-back (needs OAuth credentials + a connected account); the no-connection finalize path is verified.

## 2026-05-26

### Stage 9 — Internal Test Coverage
- New `tests-e2e/` directory under `calendar_syncing_app_web/` powered by `@playwright/test`. Smoke spec (`landing.spec.ts`) hits the marketing page and the create CTA without needing the backend. Backend-dependent specs (`organizer-flow.spec.ts`) cover attendee respond view (token-mode banner + proposals), post-finalize attendee view (Google + Outlook calendar deep-link buttons), and organizer detail confirmation panel.
- `playwright.config.ts` boots `npm run dev -- --port 3100` automatically (`webServer.reuseExistingServer`), reads `E2E_API_BASE_URL` for the backend URL, and runs a single Chromium project. CI mode (`CI=1`) enables retries and the GitHub reporter.
- `tests-e2e/helpers.ts` exposes `backendIsReachable()` (cached `GET /health` probe) so the API-dependent specs `test.skip` with a clear reason instead of failing when only the web app changed. Same module provides `seedRequestViaApi()` and `finalizeRequestViaApi()` for fixture-style setup.
- `package.json` gains `test:e2e`, `test:e2e:ui`, and `test:e2e:install` scripts. `.gitignore` excludes Playwright report/cache directories. `tests-e2e/README.md` documents the first-time `playwright install` step and the env knobs (`E2E_PORT`, `E2E_BASE_URL`, `E2E_API_BASE_URL`).
- Verified: `npx playwright test tests-e2e/landing.spec.ts` passes (1 spec). With backend down, `tests-e2e/organizer-flow.spec.ts` produces 3 skips (no false failures).

### Stage 8 — Confirmation Polish + Attendee Invites (PRD §6.7, §11)
- New `app/services/confirmation_invites.py:dispatch_confirmation_invites` sends an email-with-ICS to every participant on file with an email. The body includes the local time string, location, video link, organizer notes, and a permalink to `/v1/events/{id}/artifact.ics`.
- `app/services/notifications.py` extended with `EmailAttachment` + an `attachments` parameter on `send_notification`. SMTP mode attaches the ICS as `text/calendar`; file-outbox mode serializes attachments into the JSON so local dev can inspect them.
- New `notification_events` table (model + migration `f1b4c7d9a623`) with a partial unique constraint on `(scheduled_event_id, participant_id, kind)`. Re-finalizing the same event short-circuits via `IntegrityError`, so attendees won't be re-emailed.
- `POST /v1/requests/{id}/finalize` now writes the ICS, calls Google write-back (unchanged), then dispatches confirmation invites inline. The response payload includes `invites: {sent_count, skipped_count, participant_count, scheduled_event_id}` so the organizer UI can surface delivery state.
- Web `/events/[id]/respond` post-confirmation view replaces the single ICS link with three buttons: "Add to Google Calendar" + "Add to Outlook" use deep-link URLs synthesized from the confirmed time/location/notes; "Apple Calendar (.ics)" downloads the existing artifact endpoint.
- Web `/request/[id]` confirmed block now lists each participant with delivery status ("Invite emailed to alex@example.com" / "No email on file — share the attendee link manually") and adds an "Open attendee view" button.
- Tests: 3 new pure-function tests in `tests/test_confirmation_invites.py` cover invite body composition with full/empty optional fields and the localized time helper.

### Stage 7 — Google Calendar Read Integration (PRD §6.7)
- Backend OAuth endpoints: `GET /v1/calendar/google/connect` returns the authorize URL and an opaque `state`; `GET /v1/calendar/google/callback` exchanges the code, persists tokens to `CalendarConnection`, then 302s back to the organizer's `return_to`. State payload is base64-encoded JSON `{uid, nonce, return_to}` so we can route back the user that initiated the flow.
- `POST /v1/calendar/google/disconnect` clears `access_token`/`refresh_token` and stamps `revoked_at` on every active row. `GET /v1/calendar/connections` lists active connections with `provider_email`, `connected_at`, `expires_at`, `scopes`.
- `app/providers/google.py` gains `build_authorize_url`, `exchange_code_for_tokens`, `fetch_userinfo`, `refresh_access_token`, `ensure_fresh_access_token`, and `fetch_busy_intervals`. All three call sites (`list_calendars`, `fetch_events`, `create_event`) invoke `ensure_fresh_access_token` so a near-expired token is refreshed in place. Refresh window is 5 minutes.
- `CalendarConnection` model gains `provider_email`, `expires_at`, `updated_at`. Migration `e0a3b8d5c812` adds the columns.
- `POST /v1/requests/{id}/suggest` now loads the organizer's active Google connection, fetches busy intervals over the search window, and merges them into `blocked_intervals` before generation, so suggested slots never overlap an existing meeting.
- Settings keys added in `app/core/config.py`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `google_oauth_authorize_url`, `google_oauth_token_url`, `google_oauth_userinfo_url`, `google_oauth_scopes`. `.env.example` updated with empty placeholders.
- Web `/settings/availability` gets a Google Calendar panel above the weekly hours grid: "Connect Google" button when no row exists, "Connected to {email} → Disconnect" otherwise. Privacy copy block explains "SYZY reads when you're busy, never event titles." Callback redirects back with `?google=connected` which the page surfaces as a success toast.
- `lib/api.ts`: new `CalendarConnectionPayload` type plus `getCalendarConnections`, `startGoogleConnect`, `disconnectGoogle` helpers.
- Tests: 6 new tests in `tests/test_google_oauth.py` cover state encode/decode round trip and the four `ensure_fresh_access_token` branches (no expiry, distant expiry, near expiry, missing credentials).

### Verification
- Backend: `python -m unittest tests.test_meeting_requests tests.test_availability tests.test_scheduling tests.test_google_oauth tests.test_confirmation_invites` → 34 tests pass. 6 db-backed tests still skipped without local Postgres.
- Web: `npx tsc --noEmit` clean. Playwright landing smoke passes; backend-dependent suite skips cleanly without a backend.

## 2026-05-25 (later)

### Stage 6 — Smart "Find a Time" Slot Generation (PRD §5B, §8)
- New backend service `app/services/scheduling.py` with a deterministic 15-minute increment generator. Inputs: request date range, weekday filter, time-of-day windows, exclude dates, plus the organizer's `AvailabilityRule` weekly hours and `AvailabilityBlock` intervals from Stage 5. Scoring favors template-aligned windows, earlier dates, and slots fully inside the organizer's rule; reasons are written to `Proposal.meta` so the UI can render one-line explanations.
- New endpoint `POST /v1/requests/{id}/suggest` (schema `SuggestRequestPayload`). Supports two modes: `preview` returns suggestions without persisting; `suggest` materializes top-N as `Proposal` rows with `replace_existing=true` by default. Guarded by `can_edit_proposals` for the `suggest` mode so locked requests can still preview.
- Web `/create` page gains a "Manual poll / Find a time" mode toggle. Auto mode reveals constraint inputs (date range, weekday chips, earliest/latest local time, exclude-date list, suggestion count) and a "Preview suggestions" button that surfaces ranked slots with their `reasons[]`. Final submit materializes the previewed slots, attaches participants, and creates the share link in one flow.
- `lib/api.ts`: added `SuggestSlotPayload` type and `suggestProposals(requestId, payload)` helper.
- Tests: 8 deterministic generator tests in `tests/test_scheduling.py` cover explicit windows, exclude dates, weekday filtering, template alignment, blocked-interval overlap, dedupe, ordering, and invalid ranges.

### Stage 5 — Availability Editor (PRD §5F)
- New backend module `app/api/v1/availability.py` exposes CRUD endpoints scoped to `get_current_user`:
  - `GET /v1/availability/rules`, `PUT /v1/availability/rules` (single rule per organizer for MVP), `DELETE /v1/availability/rules/{id}`.
  - `GET /v1/availability/blocks`, `POST /v1/availability/blocks`, `DELETE /v1/availability/blocks/{id}`.
- New Pydantic schemas in `app/schemas/availability.py` (`DailyWindow`, `WeeklyHoursPayload`, `AvailabilityRuleUpsert`, `AvailabilityBlockCreate`, read models). `DailyWindow` validates `HH:MM` format and enforces `start < end`; `AvailabilityBlockCreate` enforces `start_at < end_at`. Block `type` constrained to `busy | private | ooo`.
- Router wires the new module into `/v1`.
- New web route `/settings/availability` with two panels:
  - Weekly working hours grid (per-day add/remove windows, timezone input). Default is Mon-Fri 09:00–17:00 the first time the page loads; the browser's resolved timezone seeds the field if no rule exists.
  - One-off blocks (datetime-local start/end + type select). Upcoming blocks render with a remove button.
- `lib/api.ts`: added `AvailabilityRule`, `AvailabilityBlock`, `AvailabilityWeekday`, `AvailabilityWeeklyHours`, `AvailabilityWindow` types plus `getAvailabilityRules`, `upsertAvailabilityRule`, `getAvailabilityBlocks`, `createAvailabilityBlock`, `deleteAvailabilityBlock` helpers.
- Tests: 6 schema tests in `tests/test_availability.py` cover window format, ordering, default empty hours, upsert serialization, and block ordering.

### Stage 4 — Reminder Policy + Hardening (PRD §6.5, §11)
- Backend now honors per-request reminder policy. Added `MeetingRequest.reminder_policy` (JSONB, nullable) plus a new resolver `app/services/meeting_requests.py:resolve_reminder_policy` that falls back to defaults (`initial_hours=12`, `followup_hours=24`, `max_per_participant=3`) for missing or invalid fields. `dispatch_request_reminders` now uses `policy['max_per_participant']` instead of the hardcoded constant.
- Idempotency: new `ReminderLog.reminder_sequence` column (`uq_reminder_logs_request_participant_sequence`) so a duplicate dispatch (e.g. double-tap of "Ping non-responders") short-circuits via `IntegrityError` and increments `skipped_count` instead of double-sending.
- Schema: `ReminderSettingsUpdate` and `MeetingRequestCreate` accept an optional `reminder_policy` block (`initial_hours`, `followup_hours`, `max_per_participant`, each `>= 1`). PATCH `/v1/requests/{id}/reminders` returns the resolved `policy`. `GET /v1/requests/{id}` includes `reminders.policy` and exposes up to 25 most-recent log entries (was 10) with a new `sequence` field.
- Worker: `dispatch_request_reminders` returns `{sent_count, skipped_count, outstanding_count, policy, message_preview}`. The `due_requests_stmt` initial-reminder cutoff now reads from the same default constant (`DEFAULT_INITIAL_REMINDER_HOURS = 12`).
- Web `/request/[id]` page gains numeric inputs for `initial_hours`, `followup_hours`, and `max_per_participant`, persisted via the extended PATCH. Ping button result now reads "Queued N reminders - skipped M (cap or duplicate) - K still outstanding". A new "Reminder history" timeline renders `reminders.history` with timestamp, recipient, channel, sequence, reason, and status.
- `lib/api.ts`: added `ReminderPolicy` / `ReminderPolicyInput` types, threaded through `createRequest`, `updateReminderSettings`, and `pingNonResponders` signatures.
- Migration `alembic/versions/d9e2a4b6c701_reminder_policy_and_sequence.py` adds the JSONB column, the integer sequence column (server default 1), and the partial unique constraint. Backfills existing logs by row-numbering per `(meeting_request_id, participant_id)`.
- Tests: 3 new cases in `tests/test_meeting_requests.py` cover policy defaults, overrides, and invalid-value fallback.

### Verification
- Backend: `python -m unittest discover -s tests` against the new/changed modules passes (25 pure-function tests). 6 db-backed tests skipped — local Postgres not running in this session.
- Web: `npx tsc --noEmit` clean; `npm run build` succeeds with `/settings/availability` and updated `/create` (4.78 kB) bundles.

## 2026-05-25

### Stage 3 — Attendee Experience Polish (PRD §6.4, §6.8)
- Attendee-local time display on `/events/[id]/respond`. Browser timezone is detected via `Intl.DateTimeFormat().resolvedOptions().timeZone`; proposal times now render in the attendee's tz and the page surfaces the organizer's tz as a caption ("Times shown in your local timezone (X). Organizer scheduled in Y.").
- New post-confirmation read view: when `event.status === 'confirmed'`, the respond page replaces the picker with a confirmed-time panel showing time, location, video link, notes, and an "Add to calendar (.ics)" button.
- New server-side `app/events/[id]/respond/layout.tsx` exports `generateMetadata` so iMessage/WhatsApp share-link unfurls render a useful preview (Open Graph + Twitter Card). The metadata fetches the event payload server-side for the title + first-slot preview and swaps to "confirmed" copy after finalize.
- Backend: `GET /v1/events/{event_id}/respond` and `GET /v1/share/public/{token}` now include a `confirmed_event` block (winning proposal, start/end, tz, location, video link, notes, artifact_url) when the event is confirmed. Sourced from `ScheduledEvent` so attendees never see organizer-only fields.
- Backend: new public endpoint `GET /v1/events/{event_id}/artifact.ics`. Unauthenticated, 404s unless the event is confirmed AND an artifact path is present. Powers the attendee "Add to calendar" button.
- Touch-target audit: bumped `min-height: 44px` onto `.button`, `.field input/textarea/select`, and `.inline-link` (Apple HIG minimum). `.option-card` and `.checkbox-row` were already above 44px.
- Lib types: added `ConfirmedEventPayload` and threaded it through both `EventRespondContext` and `PublicSharePayload`.

### Stage 2 — Template-Driven Create Flow (PRD §5A, §8)
- Replaced the template `<select>` on `/create` with a four-chip selector (meal / coffee / study / hangout). Each chip shows its label plus a short helper describing the duration + time-of-day window it implies. Chips are touch-target-sized (~72px tall) and stack 2-up at ≤800px, 1-up at ≤460px.
- Wired template to defaults: choosing a chip sets duration (meal 75, coffee 30, study 60, hangout 90) and pre-fills three poll slots in template-aligned windows (lunch/dinner, morning/afternoon, late afternoon/evening, afternoon/evening). User edits to duration or slots are sticky — picking another chip after that won't overwrite them. Manual "Reset to template" button surfaces once slots are touched.
- Added optional `location` and `video_link` fields to the create form; both already supported by `MeetingRequestCreate` on the backend and persisted by `POST /v1/requests`. The organizer detail page now surfaces them under the title.
- Added "Use my last settings" affordance backed by `localStorage` (key `syzy:last-create-settings`). Persists template, duration, timezone, reminder policy, location, video link, notes after a successful create. Button only renders when a saved snapshot exists.
- Extended `OrganizerRequestDetail` in `lib/api.ts` with `location` and `video_link`; backend response already includes them.

### Verification
- `npx tsc --noEmit` clean in `calendar_syncing_app_web/`.
- `npm run build` succeeds; `/create` route bundle holds at ~3.4 kB.

## 2026-05-20

### Stage 0 — Local Loop Stabilization
- Pinned local-first overrides in `calendar_syncing_app_backend/.env` (`ENV=local`, `USE_LOCAL_DATABASE_IN_DEV=true`, `USE_LOCAL_REDIS_IN_DEV=true`, dev-auth + outbox vars) so e2e flows no longer depend on remote Supabase.
- Added `safe.directory` entries for the three nested repos.
- Verified the full reminder flow end-to-end via `scripts/test_reminder_flow.py` against local Postgres + Redis + uvicorn.
- Fixed a Windows-only bug in `app/services/notifications.py:_write_outbox`: subject text containing `:` was being interpreted by NTFS as an alternate-data-stream separator, leaving 0-byte visible files. Filename builder now sanitizes the subject and appends a UTC timestamp suffix.

### Responder identity model refactor
- New event-specific participant identity model. Resolution order: logged-in user → invite token → email. Name is display-only.
- Added `Participant.invite_token`, `source` (`invited` | `public_link`), `email_verified_at`, `updated_at`. Partial unique indexes on `(event, lowercase email)` and `(event, user_id)`.
- Added `Profile.email` and `Profile.email_verified_at`.
- New service: `app/services/participants.py:resolve_participant` plus `send_magic_respond_link`. General-link responders claiming an invited email get a private invite URL emailed to that address instead of overwriting the invited row.
- New endpoints under `/v1/events/{event_id}/respond` (GET) and `/v1/events/{event_id}/responses` (POST). The legacy `/v1/share/public/{token}/responses` now delegates through the same resolver.
- Per-participant invite URLs are surfaced in `GET /v1/requests/{id}` and embedded in reminder copy so phone-only invitees still get a matchable response link.
- Organizer-verification guard (`require_verified_organizer`) applied to share-link creation, reminder ping/PATCH, and finalize. Dev-auth path returns `email_verified=True` so internal iteration isn't blocked.

### Web app
- New Next.js route `app/events/[id]/respond/page.tsx`. Token branch shows "Responding as <name>" with a locked email; general branch requires name + email with the "use the email you were invited with" helper. Handles the `check_email` magic-link response.
- Legacy `/respond/[token]` now redirects to `/events/<event_id>/respond` so existing share URLs keep working.
- Organizer detail page lists per-participant invite URLs alongside the general share link.

### Tests
- New `tests/test_participant_resolution.py` with 6 cases: invite-token match, public + new email, public + invited email → check_email, logged-in user linking by email, duplicate response upsert, general link missing email.
- `tests/test_meeting_requests.py:test_reminder_helpers` updated to verify the new per-participant URL appears in reminder copy.
- Updated `scripts/test_reminder_flow.py` to drive the new `/v1/events/{event_id}/responses` endpoint with an invite token (mirrors how an invited user clicks through from a reminder email).

### Migrations
- Added `alembic/versions/c8d1e2f3a456_event_participants_identity_model.py`.

## 2026-03-18

### Product Direction
- Pivoted the active frontend strategy from Flutter-first to Next.js-first / web-first.
- Updated the execution roadmap to align with the revised PRD and link-first mobile web launch.

### Documentation
- Added and updated [EXECUTION_ROADMAP.md](C:\Users\night\Code\Personal Projects\Calendar Syncing\EXECUTION_ROADMAP.md) for the web-first build sequence.

### Next.js Web App
- Added a new Next.js frontend in `calendar_syncing_app_web`.
- Implemented:
  - landing page
  - organizer create-request flow
  - organizer request-detail page
  - attendee response page
- Replaced the initial local demo-store prototype with real backend API calls.

### Backend Wiring
- Added local dev CORS support for the Next.js frontend.
- Added local dev organizer auth fallback for browser-based testing.
- Expanded organizer request detail payloads with:
  - participants
  - responses
  - tallies
  - progress
  - share-link info
- Added public attendee response submission on share links.

### Guest Response Model
- Kept attendee responses account-free.
- Added support for organizer invites using either email or phone.
- Added attendee response support for optional email or phone.
- Added backend participant matching by:
  - email
  - phone
  - guest key fallback

### Verification
- Next.js app builds successfully with `npm run build`.
- Backend unit tests still pass for existing request service tests.

### Repository Setup
- Initialized a dedicated Git repository for `calendar_syncing_app_web`.
- Added a web-app-specific `.gitignore` for Next.js build output, dependencies, and local env files.
- Created the initial web app Git commit: `Initial Next.js web app baseline`.
