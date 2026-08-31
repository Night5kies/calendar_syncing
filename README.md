# Calendar Syncing

Monorepo for the SYZY product. All code lives in this single Git repository:

- `backend/` — FastAPI API, Postgres, Redis, and Celery
- `web/` — Next.js web application
- `legacy/app/` — Flutter native app prototype (reference only)

## Clone

```sh
git clone git@github.com:Night5kies/calendar_syncing.git
```

## Local development

On Windows, run `./setup-local.ps1` to provision and launch the backend and web application. See `CLAUDE.md` for architecture and development notes.
