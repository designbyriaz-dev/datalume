# Status

Living document — what actually exists vs. what's planned. The sprint
table in `architecture/10-roadmap-and-acceptance.md` is the plan; this
file is the ground truth of what's built. Update it as work continues.

## Done

**Architecture Pack** (`architecture/`) — all 11 documents, covering the
88-item list from `docs/BUILD_PROMPT.md` §79. Not reviewed/approved by a
human yet — treat decisions in it as a strong starting point, not
untouchable.

**Sprint 1 — Foundation** (scaffolded and tested, not yet reviewed):

- `apps/api`: FastAPI app with organisations, workspaces, users, roles,
  memberships, sessions, audit events. Session-cookie auth (Redis-backed),
  fixed-role RBAC (`app/auth/rbac.py`), two-layer tenant scoping
  (`app/core/tenancy.py` — app-layer + Postgres RLS in the Alembic
  migration). `AdaptiveWorkspaceResolver` (`app/organisations/adaptive.py`)
  computes nav/KPIs/terminology per organisation type. Endpoints: signup,
  login, logout, me, workspace layout. 9 tests passing (SQLite + fake
  Redis — see `app/tests/conftest.py`; Postgres RLS itself is not yet
  covered by an automated test, see "Not yet done" below).
- `apps/web`: Next.js 16 app. Dark marketing/auth shell (landing,
  sign-in, sign-up) and light authenticated app shell (sidebar driven by
  the adaptive workspace layout, top bar, empty-state Home). Design
  tokens in `src/styles/tokens.css` matching `docs/DESIGN_SYSTEM.md`.
  Every other nav destination (`/properties`, `/repairs`, `/compliance`,
  etc.) is a `ComingSoon` stub, not a fabricated screen — see
  `src/components/ComingSoon.tsx`. Production build, typecheck and lint
  all pass; landing/sign-up pages visually verified in-browser.
- `infra/`: `docker-compose.yml` (postgres, redis, api, worker, web),
  Dockerfiles for api/web. **Not run end-to-end** — this machine has no
  Docker installed, so the compose stack, the Alembic migration against
  a real Postgres, and Postgres RLS itself are unverified beyond: (a) the
  migration's DDL was validated via `alembic upgrade head --sql` (offline
  mode, no live DB — confirms syntax, not runtime behaviour), and (b) the
  equivalent business logic passing against SQLite in `apps/api/app/tests`.
  **First thing to do with Docker available: `docker compose -f
  infra/docker-compose.yml up`, then run the security/tenant-isolation
  tests described in architecture/09 §2 for real, against Postgres RLS.**
- `scripts/seed_demo.py`: creates the fictional Northstar Housing org +
  a demo owner login. Foundation-only — no properties/components/etc.
  yet, since those models don't exist until later sprints.

## Not yet done

Sprints 2–24 (SaaS billing, data ingestion, every domain model, Ask
DataLume, reporting, hardening) — not started. Full order and scope in
`architecture/10-roadmap-and-acceptance.md`.

Specifically flagged as gaps to close early, not deferred to "later":

- **RLS is unverified against real Postgres.** The policy SQL in
  `alembic/versions/0001_foundation.py` is written correctly per the
  architecture but has never actually run against a live database. Treat
  tenant isolation as *unconfirmed* until the security tests in
  architecture/09 §2 exist and pass against Postgres.
- MFA fields exist on `User` but there's no enrolment/verification flow
  yet — `mfa_enabled` will always be `False` until that's built.
- No CI pipeline wired up yet (backend pytest + frontend build/lint/test
  should all gate merges once this repo has a remote).

## How to run this locally

**With Docker** (once installed): `docker compose -f infra/docker-compose.yml up`,
then in another terminal: `cd apps/api && source .venv/bin/activate &&
python ../../scripts/seed_demo.py` (or run it inside the `api` container).
Web: http://localhost:3100. API: http://localhost:8000/docs.

**Without Docker** (what this session used to verify things):
- API: `cd apps/api && python3 -m venv .venv && source .venv/bin/activate
  && pip install -e ".[dev]" && pytest` — needs Python 3.10+; this
  machine's system Python is 3.9.6, a 3.12 interpreter was fetched via
  `uv python install 3.12` for the `.venv`.
- Web: `cd apps/web && npm install && npm run build` (or `npm run dev`
  for a local server on :3100) — this alone doesn't need the API or a
  database; only signed-in pages do.
