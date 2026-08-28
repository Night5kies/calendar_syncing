# Calendar Syncing

Parent repository for the SYZY product. The application is split into three independently versioned Git submodules:

- `backend/` — FastAPI API, Postgres, Redis, and Celery
- `web/` — Next.js web application
- `app/` — Flutter native app prototype

## Clone

Clone the parent and initialize all child repositories in one command:

```sh
git clone --recurse-submodules git@github.com:Night5kies/calendar_syncing.git
```

For an existing clone:

```sh
git submodule update --init --recursive
```

## Local development

On Windows, run `./setup-local.ps1` to provision and launch the backend and web application. See `CLAUDE.md` for architecture and development notes.
