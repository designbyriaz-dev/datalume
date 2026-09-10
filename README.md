# DataLume — Property Intelligence

[![CI](https://github.com/designbyriaz-dev/datalume/actions/workflows/ci.yml/badge.svg)](https://github.com/designbyriaz-dev/datalume/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A multi-tenant B2B SaaS platform for UK housing associations, local
authorities, managing agents, and commercial landlords: a single golden
thread from development through handover into day-to-day operations —
compliance, repairs, defects, warranties, planned investment, tenancies,
rent/arrears — with a cross-domain attention engine, a grounded natural
-language "Ask DataLume" assistant, and exportable reporting on top.

All 24 sprints of the build roadmap are complete. See
[`STATUS.md`](STATUS.md) for the full sprint-by-sprint history —
what was built, real bugs found and fixed, live verification notes,
and an honest list of what's still unverified or out of scope for this
environment (Postgres RLS, real load testing, a real backup drill,
full OTel/Sentry tracing, a Playwright E2E suite). The
[`architecture/`](architecture) pack is the authoritative design
reference the build was implemented against.

## Stack

- **API** — FastAPI (Python), SQLAlchemy + Alembic, Postgres with
  row-level tenant isolation, Redis for sessions.
- **Web** — Next.js (App Router) + React + TypeScript.
- **Worker** — a plain polling loop (`app/worker/main.py`) for
  background jobs (the nightly Attention Engine scan, on-demand report
  generation) — no Celery/APScheduler, deliberately.
- **Integrations** — Stripe (billing), Anthropic (Ask DataLume's LLM
  interpretation layer), local-disk or cloud object storage for
  documents/evidence, all behind adapter boundaries with a `Null*`
  fallback when unconfigured.

## Repo layout

```
apps/
  api/            FastAPI backend — one top-level package per domain
                   (development, operations, commercial, intelligence,
                   platform, integrations, worker), plus app/tests/
  web/             Next.js frontend
architecture/      The authoritative design spec, one file per domain
infra/             Dockerfiles + docker-compose.yml for local dev
scripts/
  seed_demo.py     Seeds the two fictional demo orgs — Northstar
                   Housing and Northstar Commercial — with realistic,
                   varied data across every domain
STATUS.md          Full build history, sprint by sprint
```

## Running it locally

**With Docker:**

```bash
docker compose -f infra/docker-compose.yml up
cd apps/api && source .venv/bin/activate && python ../../scripts/seed_demo.py
```

Web: http://localhost:3100 — API: http://localhost:8000/docs

**Without Docker** (backend tests and frontend build don't need a
database at all):

```bash
# API
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest

# Web
cd apps/web
npm install
npm run build   # or `npm run dev` for a local server on :3100
```

A full browser click-through without Docker/Postgres/Redis needs a
SQLite-backed API process with an in-process fake Redis in place of the
real client — `apps/api/app/tests/conftest.py`'s fixture is the
reference implementation of that pattern; see STATUS.md's "How to run
this locally" section for the exact gotchas (importing `app.main`
before `Base.metadata.create_all`, and every module that holds its own
bound `redis_client` reference).

## Tests

```bash
cd apps/api && pytest              # 308 backend tests
cd apps/web && npm run build && npm run lint
```
