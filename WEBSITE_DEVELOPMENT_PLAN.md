# SYZY Web App — Finalized Development Plan

## Context

This plan supersedes `EXECUTION_ROADMAP.md` for active web-app work. It is written for a **continued internal iteration** posture: real organizer auth, e2e tests, and external launch hardening are deferred so that feature breadth lands first. Dev-auth fallback in the backend (`ENV=local` + `ALLOW_DEV_AUTH=true`) remains the working assumption.

### Why a new plan now

Milestones 0–2 of `EXECUTION_ROADMAP.md` are done. Milestones 3 (Reminders) and 4 (Confirmation Artifact) are **wired but unverified end-to-end** (per `ToDos.md`). The existing roadmap then jumps to Google Calendar read (M5) and smarter slot generation (M6), but the audit revealed two gaps the roadmap silently skipped:

- **Availability editor** (PRD §5F) — models (`AvailabilityRule`, `AvailabilityBlock`) exist in the backend with no endpoints and no UI. Without this, the slot generation milestone has no constraints to work from.
- **Template-driven defaults** (PRD §5A, §8) — templates are stored as a string today but do not drive duration suggestions, lunch/dinner windows, or anything else. The PRD calls this out explicitly.

This plan also front-loads **verification of already-built features** before adding new ones, so we are not stacking new code on unverified foundations.

### Changes from the existing roadmap

1. Added Stage 0 (local loop stabilization) and Stage 1 (verification of built features) before any new feature work. `ToDos.md` flags both as outstanding.
2. Added an explicit **Availability Editor** stage (Stage 5) that the existing roadmap omits, and placed it before smart slot generation so the engine has constraints to use.
3. Pulled **Google Calendar read integration** up to sit alongside slot generation (was M5/M6, now Stages 6 and 7), because slot suggestions are half-blind without organizer free/busy.
4. Demoted **organizer auth, e2e tests, and notification provider hardening** to a "launch hardening" stage (Stage 10), deferred per the internal-iteration target.
5. Split confirmation work into a separate stage (Stage 8) because the audit found one important gap: **no attendee invite email is sent on finalize** — the ICS file is built and persisted, but no job emails it.
6. Renamed milestones to "stages" and tied each to PRD sections and current code paths so the plan is executable, not just descriptive.

### Identity-model refactor (landed 2026-05-20)

The original responder flow matched by a single `contact_key` string, so an invited person who responded without entering their exact invited email ended up creating a duplicate participant row. That has been replaced with a token-first identity model:

- `Participant` now carries `invite_token`, `source` (`invited` | `public_link`), `email_verified_at`, and `updated_at`. Partial unique indexes enforce one row per `(event, lowercase email)` and `(event, user_id)`.
- A new `app/services/participants.py:resolve_participant` is the single entry point for response submission. Resolution order: logged-in `user_id` → `invite_token` → email. Name is display-only.
- Per-participant invite URLs (`/events/{event_id}/respond?token=<invite_token>`) are generated at invite time and surfaced in `GET /v1/requests/{id}`. Reminders embed each invitee's personal URL.
- General-link responders who claim an invited email get a magic-respond email instead of overwriting the invited row.
- Organizer-verification guards (`require_verified_organizer`) gate share-link creation, reminders, and finalize. Dev-auth pretends verified=True so internal iteration isn't blocked.

This means **Stage 5 (Availability Editor) onwards can assume stable participant identity.**

### Current state snapshot (from code audit)

**Web app (`calendar_syncing_app_web/`):**
- Landing, create, organizer detail, attendee respond pages all exist and call real backend APIs.
- Mobile breakpoint at 800px exists in `app/globals.css`.
- Share-link copy UI, reminder ping button, finalize/confirm UI, and ICS download link are all present on `/request/[id]`.
- Attendee response page persists a per-browser `guest_key` in localStorage and supports update-in-place.

**Backend (`calendar_syncing_app_backend/`):**
- All MVP organizer and share endpoints exist (`/v1/requests`, `/v1/share/{id}`, `/v1/share/public/{token}`, `/v1/share/public/{token}/responses`, `/v1/requests/{id}/finalize`, `/v1/requests/{id}/reminders`, `/v1/requests/{id}/reminders/ping`, `/v1/requests/{id}/artifact.ics`).
- Reminder worker (`app/workers/tasks.py`) and dispatch (`app/services/meeting_requests.py:dispatch_request_reminders`) are implemented.
- ICS generation (`app/services/confirmation_artifacts.py`) and Google write-back (`app/services/scheduled_events.py:create_google_calendar_event` via `app/providers/google.py`) are implemented.
- Availability models exist but have **no endpoints**. Slot generation **does not exist**. Google OAuth connect endpoint **does not exist**. Attendee ICS invite email job **does not exist**.

---

## Stages

### Stage 0 — Local Loop Stabilization (1–2 days)

**Problem:** End-to-end testing currently depends on remote Supabase because of mis-set `DATABASE_URL` precedence. Nested-repo `safe.directory` issues block normal `git` use in subprojects (`ToDos.md`).

**Deliverables:**
- Verified `.env` setup in `calendar_syncing_app_backend/` keeps `ENV=local`, `USE_LOCAL_DATABASE_IN_DEV=true`, `USE_LOCAL_REDIS_IN_DEV=true` so `app/core/config.py:effective_database_url` returns the local URL.
- `docker compose up -d db redis` + `alembic upgrade head` succeeds against the local Postgres.
- `python scripts/test_reminder_flow.py` runs green against `http://127.0.0.1:8000`.
- `git config --global --add safe.directory` entries added for the two nested repos.

**Acceptance:** Smoke script exits 0 without touching remote Supabase. `git status` works inside both nested repos without admin prompts.

**Critical files:** `calendar_syncing_app_backend/.env`, `calendar_syncing_app_backend/scripts/test_reminder_flow.py`, `calendar_syncing_app_backend/app/core/config.py:42`.

---

### Stage 1 — Verification of Built Features (2–3 days)

**Problem:** Reminders, ICS generation, and Google write-back are wired but unverified end-to-end (`ToDos.md`). Building more on top is risky.

**Deliverables:**
- Manual walk: create request in `/create`, share link, respond from `/respond/[id]`, ping non-responders, observe entries in `dev_outbox/`, finalize, download ICS from `/v1/requests/{id}/artifact.ics`.
- Run Celery worker and confirm `enqueue_due_reminders` picks up due requests via `due_requests_stmt` and respects `MAX_REMINDERS_PER_PARTICIPANT = 3` (`app/services/meeting_requests.py:14`).
- Test against a real Google account connected via the existing `CalendarConnection` row (insert manually for now) and confirm `app/services/scheduled_events.py:create_google_calendar_event` returns a `provider_event_id`.
- Log every defect found into `ToDos.md` and resolve P0/P1 before moving on.

**Acceptance:** Each PRD MVP feature A–E is demonstrably working in local end to end. Open issues are tracked, not silent.

**Critical files:** `app/workers/tasks.py`, `app/services/meeting_requests.py`, `app/services/scheduled_events.py`, `app/providers/google.py`.

---

### Stage 2 — Template-Driven Create Flow (PRD §5A, §8) (3–4 days)

**Problem:** Templates today are a `<select>` dropdown that does not change anything else on the page. PRD explicitly calls for meal-tuned defaults.

**Deliverables in `calendar_syncing_app_web/app/create/page.tsx`:**
- Replace dropdown with a four-chip selector (meal / coffee / study / hangout) — touch-target-sized.
- Template drives duration default (meal 75, coffee 30, study 60, hangout 90) and suggested time-of-day windows surfaced as pre-filled poll slots the organizer can edit.
- Add optional `location` and `video_link` fields (both already on `MeetingRequest` model).
- Add a "Use my last settings" affordance backed by localStorage so repeat organizers move faster.

**Backend dependency:** none. `MeetingRequest` already accepts `location`, `video_link`, `event_type`.

**Acceptance:** Picking a template visibly changes duration and pre-fills suggested poll slots. Location and video link round-trip through `/v1/requests` and appear on `/request/[id]`.

**Critical files:** `calendar_syncing_app_web/app/create/page.tsx`, `calendar_syncing_app_web/lib/api.ts:118-131` (`createRequest` payload).

---

### Stage 3 — Attendee Experience Polish (PRD §6.4, §6.8) (2 days)

**Problem:** `/respond/[id]` shows times in `request.timezone`, not the attendee's local timezone. PRD says "show attendee-local time always." Share links also have no OG metadata, so chat unfurls look bare.

**Deliverables:**
- Attendee-local time display in `/respond/[id]/page.tsx`: detect browser tz, render proposal times in it, and show the request's origin tz as a small caption ("organizer's tz: America/New_York").
- Mobile touch-target audit: all interactive elements ≥44px tall.
- Open Graph + Twitter Card metadata on the share landing route so iMessage/WhatsApp unfurls render a useful preview.
- Post-confirmation read view for attendees who revisit the link: shows the confirmed time + "Add to calendar" button using the ICS download endpoint.

**Backend dependency:** the public share payload already exposes the request's timezone (`PublicSharePayload.request.timezone`); no schema change needed. The post-confirm view needs `/v1/share/public/{token}` to include the confirmed `ScheduledEvent` when status is `confirmed` — small additive change to `app/api/v1/share.py`.

**Acceptance:** Opening a share link in a browser set to a different tz shows the proposal times in the browser's tz. Sharing the link in iMessage shows a rich preview. Re-opening after confirm shows the winner + ICS button.

**Critical files:** `calendar_syncing_app_web/app/respond/[id]/page.tsx`, `calendar_syncing_app_web/lib/types.ts:formatRange`, `calendar_syncing_app_backend/app/api/v1/share.py`.

---

### Stage 4 — Reminder Policy + Hardening (PRD §6.5, §11) (3–4 days)

**Problem:** Backend has a `reminder_policy` JSONB column but it is ignored — `MAX_REMINDERS_PER_PARTICIPANT` is a hardcoded constant. The web UI exposes only on/off and a deadline. Idempotency relies on the cap rather than a stable key (audit finding).

**Deliverables (backend):**
- Honor `reminder_policy` JSONB on `MeetingRequest`: `{initial_hours, followup_hours, max_per_participant}` overrides the default.
- Add an idempotency key on `ReminderLog` (`meeting_request_id, participant_id, reminder_sequence`) and have `dispatch_request_reminders` short-circuit on duplicates.
- Decide outbox vs SMTP for local (`ToDos.md`): keep file outbox as the default but document how to flip `NOTIFICATION_MODE=smtp` for staging tests.

**Deliverables (web):**
- Expand the reminder controls on `/request/[id]/page.tsx`: numeric inputs for `initial_hours` and `followup_hours`, and a hard cap for `max_per_participant`. Persist via the existing `PATCH /v1/requests/{id}/reminders` (extend its schema).
- Render the existing `reminders.history` array as a sent-log timeline.
- Surface ping outcome (sent / skipped / outstanding counts) more clearly — these come back from `pingNonResponders`.

**Acceptance:** Editing policy values changes worker behavior in a local run. Calling ping twice in a row does not double-send. The history panel matches what the worker logged.

**Critical files:** `calendar_syncing_app_backend/app/services/meeting_requests.py`, `calendar_syncing_app_backend/app/models/reminder_log.py`, `calendar_syncing_app_backend/app/schemas/meeting_request.py:ReminderSettingsUpdate`, `calendar_syncing_app_web/app/request/[id]/page.tsx`.

---

### Stage 5 — Availability Editor (PRD §5F) (4–5 days)

**Problem:** `AvailabilityRule` and `AvailabilityBlock` tables exist with no endpoints and no UI. Slot generation (Stage 6) needs these as inputs.

**Deliverables (backend):**
- CRUD endpoints under `/v1/availability/rules` and `/v1/availability/blocks` (organizer-scoped via existing `get_current_user`).
- Pydantic schemas in `app/schemas/availability.py`.

**Deliverables (web):**
- New route `app/settings/availability/page.tsx` with two sections: a weekly working-hours grid (rules) and a list of one-off private blocks (blocks).
- Mobile-friendly grid: tap-and-drag is overkill at this stage; start with start/end inputs per day.

**Acceptance:** Organizer can set working hours (e.g., Mon-Fri 9-17) and add a private block (e.g., "blocked Thu 14:00-16:00 next week"). Records round-trip through the new endpoints.

**Critical files:** new `app/api/v1/availability.py` and `app/schemas/availability.py` in the backend; new `app/settings/availability/page.tsx` in the web.

---

### Stage 6 — Smart "Find a Time" Slot Generation (PRD §5B, §8) (5–7 days)

**Problem:** Slot generation does not exist in the backend. Today the create flow forces organizers into a manual poll. Manual poll stays for large groups, but small-group meal/coffee should auto-suggest.

**Deliverables (backend):**
- New service `app/services/scheduling.py` with a deterministic generator at 15-minute increments.
- Inputs: request constraints (date range, days-of-week, time-of-day windows, exclude dates — all new constraint fields on the schema), organizer availability rules + blocks (Stage 5), template windows.
- Scoring: prefer template-aligned windows, prefer sooner, store transparent reasons in `Proposal.meta`.
- Endpoint `POST /v1/requests/{id}/suggest` that materializes top-N suggestions as `Proposal` rows.

**Deliverables (web):**
- On `/create/page.tsx`, add a "Find a time" toggle alongside the existing "Manual poll" mode.
- Constraints UI: date range picker, days-of-week chips, time-of-day window inputs, exclude dates.
- After submit, show generated suggestions with a one-line "why this slot" reason from `Proposal.meta`.

**Acceptance:** "Meal" template with no organizer availability blocks generates ~5 suggestions in lunch/dinner windows over the next 7 days. Suggestions respect availability blocks from Stage 5.

**Critical files:** new `app/services/scheduling.py` + `app/api/v1/requests.py:suggest`, `calendar_syncing_app_web/app/create/page.tsx`, `calendar_syncing_app_web/lib/api.ts`.

---

### Stage 7 — Google Calendar Read Integration (PRD §6.7) (4–5 days)

**Problem:** Backend can write to Google Calendar but cannot read free/busy — there is no OAuth connect endpoint, so `CalendarConnection` rows only exist if inserted manually. Without read, slot suggestions (Stage 6) cannot factor in the organizer's real calendar.

**Deliverables (backend):**
- OAuth connect endpoints: `GET /v1/calendar/google/connect` (returns auth URL), `GET /v1/calendar/google/callback` (exchanges code, stores tokens in `CalendarConnection`).
- Token refresh path in `app/providers/google.py` invoked from `fetch_events` / `create_event` when access token is near expiry.
- Wire `fetch_events` into Stage 6's `suggest` endpoint so generated slots avoid busy times.

**Deliverables (web):**
- Connect/disconnect UI on `/settings/availability/page.tsx` (added in Stage 5).
- Privacy copy ("SYZY reads when you are busy, never event titles") rendered prominently.

**Acceptance:** Organizer can connect their Google account, see "Connected to {email}" in settings, and slot suggestions skip any times they are busy.

**Critical files:** new endpoints in `app/api/v1/calendar.py`, `app/providers/google.py:29` (`fetch_events`) and the still-to-add token refresh path, `app/settings/availability/page.tsx`.

---

### Stage 8 — Confirmation Polish + Attendee Invites (PRD §6.7, §11) (3 days)

**Problem:** Audit found one real gap in the confirmation flow: when an organizer finalizes a request, the ICS is built and persisted but **never emailed to attendees**. Today they only learn about the confirmed time if they revisit the share link or the organizer pings them.

**Deliverables (backend):**
- New Celery task `send_confirmation_invites(scheduled_event_id)` triggered from `finalize_scheduled_event`. Sends the ICS to every participant with email, logs to `notification_events` (table mentioned in PRD §9 — verify or add migration).
- SMS skipped (still stub) — out of scope for internal iteration.

**Deliverables (web):**
- Clearer post-confirmation block on `/request/[id]/page.tsx` (currently a small summary, `ToDos.md` flagged it).
- "Add to Google Calendar" / "Add to Apple Calendar" buttons on `/respond/[id]/page.tsx`'s post-confirm view (from Stage 3), generating the standard universal calendar URLs from the ICS data.

**Acceptance:** Finalizing a request writes the event to Google Calendar AND triggers email-with-ICS to every attendee with an email address. Re-finalizing the same event does not double-send (idempotency via `scheduled_event_id`).

**Critical files:** `app/services/scheduled_events.py:finalize_scheduled_event`, new `app/workers/tasks.py:send_confirmation_invites`, `calendar_syncing_app_web/app/request/[id]/page.tsx`, `calendar_syncing_app_web/app/respond/[id]/page.tsx`.

---

### Stage 9 — Internal Test Coverage (2–3 days)

**Problem:** No automated frontend tests exist (`ToDos.md`). Even for internal iteration, every regression has to be caught manually today.

**Deliverables:**
- Playwright suite under `calendar_syncing_app_web/tests-e2e/` covering: organizer create + share, attendee respond, organizer finalize, post-confirm view.
- A `npm run test:e2e` script that spins up the dev server and runs against a `docker-compose`-managed local backend.
- Lightweight CI hook (optional) that runs the suite on each web-app branch.

**Acceptance:** Running `npm run test:e2e` from a clean local environment runs end-to-end without manual intervention and surfaces a regression if the backend payload shape changes incompatibly.
      
**Critical files:** new `calendar_syncing_app_web/tests-e2e/` directory, `calendar_syncing_app_web/package.json`.

---

### Stage 10 — Launch Hardening (deferred until launch shape is chosen)

This stage exists to make the eventual transition from internal iteration to closed beta or public launch a single, scoped chunk of work rather than a thousand small surprises. **Do not start until launch shape is decided.**

- **Organizer auth via Supabase**: replace dev-auth fallback. Email magic link or Google sign-in. Inject bearer token in `lib/api.ts`. Enforce ownership on `/request/[id]`.
- **Google write-back retries** and **token refresh job** in `app/workers/tasks.py`.
- **Expired-link cleanup job** and configurable token TTL on `ShareLink`.
- **Real SMS provider** (Twilio or similar) replacing the outbox stub.
- **CORS + cookies hardening** for production origins.
- **Lighthouse + accessibility pass** on the mobile flows.

---

### Stage 11 — Post-MVP Expansion (PRD §13 Phase 4, §15)

- PWA installability and offline shell.
- Outlook + Apple Calendar integration parity.
- Persistent friend-availability sharing (PRD V1 Tier A).
- Organizer dashboard for past + recurring requests.
- Native wrapper exploration only if web retention warrants it.

---

## Verification (across all stages)

For each stage:

1. **Backend changes:** `python -m unittest discover -s tests` from `calendar_syncing_app_backend/`. Add a focused test next to the change before claiming done.
2. **End-to-end:** `python scripts/test_reminder_flow.py` after each stage to catch shape regressions cheaply.
3. **Local manual smoke** of the affected web route in a real mobile browser (DevTools mobile emulation minimum, real device when possible).
4. **Outbox inspection:** for anything reminder- or invite-shaped, eyeball `dev_outbox/` JSON to confirm the right thing was queued.
5. **From Stage 9 onward:** `npm run test:e2e` from `calendar_syncing_app_web/` is the final gate before marking work done.

## What this plan deliberately does not do

- It does not add native mobile work — the legacy Flutter app stays a reference only.
- It does not introduce a friend graph, persistent profiles, or social features. Those are V1+.
- It does not optimize for production observability (Sentry, structured logging, traces). That belongs in Stage 10.
- It does not block any stage on the next stage's existence — Stages 2, 3, 4 are independently shippable.
