# SYZY Execution Roadmap

This roadmap reflects the updated PRD direction:

- product surface: Next.js-first website
- primary entry point: shared link in a text or group chat
- backend: keep the existing FastAPI service and evolve it for web/mobile-browser flows
- native app: later, only after the link-first web loop proves demand

## Strategic Shift

The old Flutter-first prototype assumed people would enter the product through an app-like shell.
The revised PRD correctly changes the wedge:

1. Organizer creates request in web app.
2. Organizer shares a link in chat.
3. Attendees open the link in mobile web.
4. Attendees respond without an account.
5. Organizer confirms a winner.
6. Calendar write-back and ICS make the plan feel real.

That lowers first-response friction, which is the highest-leverage change in this pivot.

## Current Repo Shape

- `calendar_syncing_app_backend`: existing FastAPI backend with request, proposal, participant, share, and calendar models/routes
- `calendar_syncing_app_frontend`: legacy Flutter prototype kept for reference
- `calendar_syncing_app_web`: new Next.js web frontend for the web-first launch

## Build Principle

Do not try to recreate a native app in the browser.
Build a fast mobile web workflow that feels natural when opened from a shared link.

The website wins if it reduces organizer labor:

- create a request quickly
- share a link quickly
- collect responses cleanly
- show who has not responded
- confirm a winner

## Milestone 0: Web-First MVP Lock

Objective:
- Lock the product to a link-first mobile web MVP.

Must be true:
- website is the primary surface
- organizer flow works in browser
- attendee response flow works in browser
- no install required for guests
- no dependency on native auth/app flows for first response

Out of scope for this milestone:
- native app polish
- rich social graph
- persistent friend sharing
- attendee calendar connections
- advanced messaging

Exit criteria:
- the team treats Next.js as the launch frontend
- all roadmap language and implementation priorities follow the web-first assumption

## Milestone 1: End-To-End Browser Loop

Objective:
- Prove the organizer-to-attendee flow in web.

Frontend:
- landing page
- organizer create request page
- organizer request detail page
- attendee response page
- mobile-first responsive layout
- internal deep-link routes for request/respond

Backend:
- request creation API
- participant add API
- proposal add API
- share link creation API
- public share payload API
- response submission API
- finalize API

Exit criteria:
- organizer can create a request in the web app
- attendee can respond from a shared link on mobile browser
- organizer can see responses and confirm a winner

## Milestone 2: Real Share Links And Request Progress

Objective:
- Replace placeholder/demo link behavior with real server-backed flows.

Frontend:
- real copied share URLs
- request progress view
- attendee response success state
- organizer confirmation summary

Backend:
- richer share payload with proposals
- request detail payload with tallies and outstanding participants
- request progress endpoint or equivalent detail expansion

Exit criteria:
- copied links open the actual attendee response page
- organizer can tell who responded and what is winning without leaving the page

## Milestone 3: Reminders

Objective:
- Remove follow-up burden from the organizer.

Backend:
- reminder policy fields
- reminder worker jobs
- idempotency and send logging
- manual ping endpoint

Frontend:
- reminder controls in organizer page
- visible progress toward response deadline

Exit criteria:
- organizer can ping non-responders
- reminder automation works without duplicate sends

## Milestone 4: Confirmation Artifact

Objective:
- Make the final plan feel real.

Backend:
- ICS generation
- organizer calendar write-back
- final event payload

Frontend:
- confirmed plan summary
- invite/ICS affordance

Exit criteria:
- confirmation creates a final artifact worth sharing back into chat

## Milestone 5: Google Calendar Read Integration

Objective:
- improve organizer slot quality after the web loop proves itself

Scope:
- organizer-only Google connection
- free/busy read
- privacy-safe wording

Exit criteria:
- organizer gets better suggestions without adding attendee friction

## Milestone 6: Smarter Slot Generation

Objective:
- accelerate request creation without increasing friction

Scope:
- template-aware suggestions
- deterministic ranking
- explainable slot reasons

Do not block launch on this.
Manual polls still matter for large groups and should remain supported.

## Milestone 7: Expansion

Only do this once the web loop shows repeat use:

- PWA installability
- SMS reminders
- Outlook integration
- richer organizer account area
- native wrapper or real mobile apps
- persistent relationship features

## What To Build Next

Near-term priority:

1. Finish the Next.js frontend structure.
2. Connect the Next.js pages to the existing FastAPI backend.
3. Replace all local demo storage with real request/share/response API calls.
4. Add organizer progress/tally data.
5. Add real share links that open browser-safe attendee pages.

## Repo-Level Recommendation

Short term:
- treat `calendar_syncing_app_web` as the active frontend
- keep `calendar_syncing_app_frontend` only as a legacy prototype

Later:
- either archive the Flutter app or rebuild native surfaces only after the web-first product proves retention
