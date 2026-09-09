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

**Sprint 2 — SaaS / Billing** (the non-Stripe half; Stripe itself deferred
per instruction — "continue with sprint 2, billing later"):

- `apps/api/app/platform/billing.py`: `Plan`, `Subscription`,
  `UsageRecord` models; a `PLAN_CATALOG` (Starter/Professional/Business/
  Enterprise, pricing from `docs/BUILD_PROMPT.md` §64, money stored as
  integer pence) lazily upserted into the DB the same way system roles
  are — `ensure_plan_catalog_seeded` keeps the full catalog visible
  regardless of which plans anyone has actually subscribed to yet.
  Signup now creates a 14-day `TRIALING` Starter subscription
  automatically, matching the "no credit card required" marketing copy.
- `app/platform/entitlements.py`: `require_entitlement(key)`, same
  composition pattern as `require_permission` — not yet used by any real
  feature-gated route (nothing exists yet that needs gating), tested
  directly instead.
- `app/integrations/billing_provider.py`: the `BillingProvider` adapter
  boundary architecture/07 §2 calls for. Only `NullBillingProvider` is
  implemented — every checkout/portal call fails loudly with a 503 and a
  specific "billing is not configured" message rather than crashing or
  silently succeeding. `StripeBillingProvider` is the next thing to add
  once Stripe credentials exist; nothing else should need to change
  shape when it lands, since routes only depend on the `BillingProvider`
  Protocol.
- `/api/v1/subscriptions` (get current + entitlements), `/plans` (list
  catalog), `/checkout` and `/portal` (both `billing.manage`-gated,
  currently always 503 via `NullBillingProvider`).
- `apps/web`: `/organisation/billing` is now real — current
  plan/trial-countdown card, all four plans, Upgrade buttons that call
  checkout and show the "not configured yet" message inline rather than
  a broken redirect. Verified end-to-end in-browser (signup → Home →
  Billing → Upgrade click) against a local SQLite+fake-Redis smoke-test
  run of the API — see "Without Docker" below.
- 8 new backend tests (17 total passing): trial subscription on signup,
  full catalog listing, checkout permission boundary (OWNER passes
  permission and hits 503; VIEWER is correctly 403'd before ever reaching
  the billing provider), `NullBillingProvider` behaviour,
  `resolve_entitlements` edge cases.
- Found and fixed along the way: `require_permission` gave a confusing
  403 ("missing permission") instead of 400 when `X-Organisation-Id` was
  simply missing — now checked first, same as `get_tenant_db` already
  did. Frontend also hit two real Next.js 16 / React Compiler ESLint
  rules (`react-hooks/set-state-in-effect`, `react-hooks/immutability`)
  that didn't exist in earlier eslint-config-next — fixed rather than
  suppressed (see `organisation/billing/page.tsx`).

**Sprint 3 — Data Ingestion & Provenance:**

- `app/core/provenance.py`: `ProvenanceMixin` (source_type, source_system,
  source_dataset_id, import_job_id, original_reference, created_by/at,
  updated_by/at) — no real consumer table exists yet (domain entities
  start Sprint 5), so it's tested against a throwaway table
  (`app/tests/test_provenance.py`) ahead of time rather than left
  unverified until something depends on it.
- `app/ingestion/`: `Dataset` / `ImportJob` / `ImportRow` /
  `MappingTemplate` models, and the pipeline (`pipeline.py`):
  UPLOAD → VALIDATE → UNDERSTAND → MAP → REVIEW → IMPORT, exactly the
  staging-table shape architecture/02 §2 specifies (never parse-and-insert
  directly). `/api/v1/uploads` (multipart CSV), `/api/v1/datasets`
  (list/detail/rows), `/mapping` (apply + persist as a reusable
  per-org-per-dataset-type template), `/import`.
- Two dataset types seeded as field dictionaries (`PROPERTIES`,
  `COMPONENTS`) — enough to exercise the pipeline for real; the rest of
  spec §13's dataset list gets a dictionary each as its domain lands.
- Simplifications, each documented at the point they matter (mainly
  `pipeline.py`'s module docstring): **CSV only**, no XLSX/XLS yet.
  VALIDATE/UNDERSTAND run **synchronously** in the upload request, not as
  an RQ-backed background job — the DB shape already matches the
  background-job design, so moving it later is a call-site change, not a
  schema change; not done yet because there's no Redis available in this
  environment to verify a real job queue against (same reasoning as
  Sprint 2's Stripe deferral — build what's genuinely testable now).
  **No object storage** — uploaded files are parsed in memory and
  discarded, not persisted; real file retention is a Sprint 4 (Documents)
  concern. **IMPORT is a registered-importer seam** (`IMPORTERS` dict) —
  empty in Sprint 3 since no canonical domain tables exist to import
  into; running it today is an honest no-op (rows move to `IMPORTED`,
  zero entities created, `importer_registered: false` in the response),
  not a fake success.
- Cleaning: whitespace trimming only, logged per-row
  (`raw_data["_cleaning"]`) so it's visible on review, never silent.
- `apps/web`: `/data-and-uploads` is real — upload form, a mapping-review
  table (dropdown per column, pre-filled from the proposed/template
  mapping), apply/import buttons, and a dataset list. Verified two ways:
  the automated test suite, and real `curl` multipart requests against a
  live (SQLite-backed) run of the API — **the Browser pane's tools
  cannot drive a native file picker** (`form_input` on a `type="file"`
  input throws `InvalidStateError`, a real browser security restriction,
  not a tool bug), so the file-selection step itself was verified via
  curl + pytest rather than a full GUI click-through; everything else
  (empty state, the populated dataset list after a curl-driven upload,
  the 401→sign-in redirect) was verified in-browser.
- 15 new backend tests (32 total passing).
- **A real bug found by hand-testing, not by the original test suite:**
  an unescaped comma in a test CSV ("Flat 4, Oak House") produced one
  extra cell; the pipeline silently truncated it, shifting every
  subsequent field left and marking the corrupted row VALID/IMPORTED.
  Root cause was that every test fixture happened to be well-formed CSV,
  so nothing exercised a ragged row. Fixed: a cell-count mismatch is now
  flagged `INVALID` at staging time with a specific message and excluded
  from import; regression-tested
  (`test_ragged_row_is_flagged_not_silently_misaligned`) using the exact
  malformed input that surfaced it.

**Sprint 4 — Manual Entry / Documents / Evidence** (the Documents half;
"Manual Entry" itself is still conceptual — see below):

- `app/integrations/storage.py`: `DocumentStorage` Protocol +
  `LocalFilesystemStorage` — unlike Stripe (Sprint 2) and a real job
  queue (Sprint 3), local-disk storage needs no external credentials, so
  this is a genuine working implementation, not a deferred stub. A cloud
  adapter (S3/Azure Blob) is a second implementation behind the same
  Protocol when this runs somewhere with those credentials.
- `app/documents/`: `Document` model — append-only versioning (spec §28:
  "never silently overwrite previous versions"). A new version is a new
  row; the prior row is marked `SUPERSEDED` and linked via
  `superseded_by_document_id`, never edited in place. All versions of one
  document share a `lineage_id` so "get the version history" is a plain
  query, not a linked-list walk. `related_entity_type`/`related_entity_id`
  is a plain polymorphic reference (no FK) so a document can attach to
  anything — including entity types that don't have a table yet.
  `document_reference` (e.g. `DOC-000001`) is a simple per-org sequential
  counter, explicitly interim: it is **not concurrency-safe** under
  simultaneous uploads (a `COUNT`-based number, not row-locked) — the
  real configurable Identifier & Reference Engine is Sprint 7; this
  format is retired then, not extended.
- `/api/v1/documents` (upload), `/{id}/versions` (new version — rejects
  versioning from a stale/superseded row), `/{id}` (detail + full version
  history), `/{id}/download`, `/` (list, filterable by related entity,
  defaults to current versions only).
- **Real integration with Sprint 3, not just parallel infrastructure:**
  the ingestion upload endpoint now retains the raw uploaded CSV as a
  `Document` (`related_entity_type="dataset"`) instead of discarding it
  after parsing — closing the "no object storage" gap Sprint 3 flagged.
  `Dataset.source_file_document_id` replaces the placeholder storage-key
  field from Sprint 3.
- `apps/web`: `/data-and-uploads` gained a Documents section (upload
  form, current-version list, download) and a download link on each
  dataset's source file. Verified in-browser end-to-end, including
  clicking Download and confirming the real network request succeeded
  with no console errors — the file-selection step itself was again
  verified via curl (see Sprint 3's note on why the Browser pane can't
  drive a native file picker), but everything downstream of an upload
  (versioning, supersession, the current-only list filter, download) was
  exercised for real in the browser this time, not just via curl.
- 9 new backend tests (41 total passing), including a round-trip proof
  that an old version's bytes remain unmodified and downloadable after a
  new version supersedes it.
- **"Manual Entry" is not built as its own feature in Sprint 4** — the
  architecture's description ("every '+Add X' form is a thin wrapper over
  the same service functions the import pipeline calls") needs a
  canonical domain entity to add, and none exist until Sprint 5. Document
  upload itself *is* a manual-entry-shaped flow (RBAC-checked, audited,
  no separate "manual record" model) and proves the pattern; the first
  domain "+Add" form is Sprint 5's.

**Sprint 5 — Property Model & Data Quality:**

- `app/core/provenance.py`'s `ProvenanceMixin` gets its first real
  consumer: `app/development/models.py`'s `Property` and `Space`. No
  `development_id`/`building_id`/`floor_id` yet — those tables don't
  exist until Sprint 6 (Development Hierarchy); a standalone property
  (existing stock, no development context) is exactly as valid as one
  created through a development later, matching the architecture's
  nullable-parent-chain design. `property_reference` (`PROP-000001`) is
  the same interim per-org sequential counter pattern as documents,
  carrying the same "not concurrency-safe, Sprint 7 replaces it" caveat.
- `app/development/service.py`'s `create_property`/`create_space` are
  the shared functions manual entry and import both call — the promise
  from Sprint 4's STATUS note is now real: `POST /api/v1/properties` and
  `IMPORTERS["PROPERTIES"]` (`app/development/importers.py`) both call
  the same function, both produce identical, equally valid, fully
  audited records.
- **`IMPORTERS["PROPERTIES"]` is now registered** — the ingestion
  pipeline's "honest no-op" (Sprint 3) creates real `Property` rows for
  this dataset_type now, with full provenance (`source_dataset_id`,
  `import_job_id`, `original_reference` set to the source row number).
  Registration happens as an import-time side effect
  (`app/development/importers.py`, imported once by `app/main.py`) so
  `app/ingestion/pipeline.py` never has to import the development
  module — the seam stays generic. `COMPONENTS` still has no importer,
  so the "honest no-op" path is still directly tested, just against that
  dataset_type instead now.
- To make this work, `IMPORTERS`' callable signature changed from
  `(db, organisation_id, mapped_fields)` to
  `(db, dataset, import_job, row, mapped_fields)` — the org-only version
  couldn't carry real provenance back to the row it came from.
- `app/data_health/rules.py`: rule registry v1 — `MISSING_PROPERTY_TYPE`,
  `MISSING_UPRN`, `MISSING_POSTCODE`, `DUPLICATE_PROPERTIES` (normalized-
  address match). Each rule is a plain, independently testable function;
  `GET /api/v1/data-health` recomputes fresh on every call (same
  synchronous-for-now simplification as the ingestion pipeline) and
  returns both the headline score and every contributing check's own
  pass ratio — never just the number. Score is an unweighted mean of
  per-check pass ratios; spec's "configurable weights" is unimplemented
  (v1 is deliberately the simplest transparent version).
- `apps/web`: `/properties` (list + manual add form) and
  `/properties/[id]` (detail + spaces) are real, and Home now shows
  actual KPI cards (Total Properties, Data Health Score) once any
  property exists instead of always showing the empty state. The
  `/properties/[id]` route is Next.js 16's first dynamic route in this
  app — `params` is async per the version-16 breaking change, handled
  with a thin server-component wrapper (`page.tsx`) that awaits it and
  hands a plain string down to a client component
  (`PropertyDetailClient.tsx`) that does the actual data fetching.
- 14 new backend tests (55 total passing). Verified in-browser
  end-to-end this time with no curl fallback needed for the core flow
  (unlike Sprints 3-4, nothing here requires a native file picker): signed
  up, added a property through the real form, opened its detail page,
  added a space, and watched Home's KPI cards update — 75% Data Health
  Score matched the hand-computed expected value (missing UPRN is the
  only failing check of four). The CSV-to-Property import path was
  additionally verified via curl against the live server to directly
  observe the full provenance chain in the response JSON.

**Sprint 6 — Development Hierarchy:**

- `app/development/models.py` adds `Development`, `Building`, `Floor`
  and wires them into `Property`/`Space` (Sprint 5): `Property` gets
  nullable `development_id`/`building_id`/`floor_id`; `Space` gets a
  nullable `building_id` alongside its now-nullable `property_id`, with
  a `CHECK` constraint requiring at least one parent. Every level except
  Property stays optional — a standalone property (no development
  context) is still exactly as valid as a fully-drilled-down one, same
  design principle as Sprint 5, just extended up the tree.
- `resolve_property_hierarchy` (`app/development/service.py`) is the one
  genuinely non-trivial piece: a property can be linked at any level, and
  the levels must agree with each other. Given a `floor_id`, its
  `building_id` is derived (never trusted from the caller); given a
  `building_id`, its `development_id` is derived the same way.
  Contradictory input (a `floor_id` that belongs to a different
  `building_id` than the one also supplied) is a 400
  (`HierarchyMismatchError`); an id that doesn't exist in the org is a
  404 (`HierarchyNotFoundError`). `create_building`/`create_floor` reuse
  the same two exceptions for their own parent-existence checks.
  `create_development`/`create_building`/`create_floor` follow the
  established reference-generator pattern (`DEV-000001`, `BLD-000001`,
  same "not concurrency-safe, Sprint 7 fixes it properly" caveat as
  documents/properties); floors are identified by name, not a generated
  code, matching how they're actually referred to.
  `GET /api/v1/developments/{id}/hierarchy` composes the full tree
  (buildings → floors, with a property count at every level including
  properties linked partway down — e.g. to a building but no floor yet)
  — this is the "hierarchy queries" item from the roadmap row.
- No CSV import path for developments/buildings/floors this sprint —
  `IMPORTERS` only has `PROPERTIES` still. Manual entry only, via
  `app/development/hierarchy_router.py`.
- `apps/web`: `/developments` (list + add), `/developments/[id]`
  (hierarchy tree + add building), `/buildings` (list + add, optional
  development link), `/buildings/[id]` (floors + properties on that
  building + add floor). `/properties`'s add form gained an optional
  Building dropdown, and the property detail page now shows a linked
  Building with a working link back. Two more Next.js 16 async-params
  dynamic routes, same thin-wrapper pattern as `/properties/[id]`
  (Sprint 5). Factored the repeated form/button inline styles used
  across properties/developments/buildings into
  `src/components/formStyles.ts` once a fourth page needed them.
- 12 new backend tests (67 total passing). Verified end-to-end in the
  browser building the full chain by hand — created a development,
  added a building under it, added a floor, then added a property linked
  to the building (not the floor) via the Properties page's new
  dropdown — and confirmed the hierarchy view on the development page
  correctly read "1 floor · 1 property (1 unassigned to a floor)",
  matching the exact state created. The property detail page's Building
  link was also confirmed to resolve to the right building.

## Not yet done

Sprints 7–24 (identifiers & asset coding, every remaining domain model,
Ask DataLume, reporting, hardening) — not started. Full order and scope
in `architecture/10-roadmap-and-acceptance.md`.

Specifically flagged as gaps to close early, not deferred to "later":

- **Document, property, development and building references aren't
  concurrency-safe.** All four reference generators are `COUNT`-based —
  two simultaneous creates for the same org could theoretically collide.
  Real fix is the Sprint 7 Reference Engine (row-locked counters), not a
  patch here.
- **No CSV import for developments, buildings or floors.** Only
  `PROPERTIES` has a field dictionary and a registered importer; adding
  the others is straightforward (same pattern as
  `app/development/importers.py`) but wasn't needed for this sprint's
  stated scope.
- **The ingestion pipeline has no background job queue yet.**
  VALIDATE/UNDERSTAND run synchronously inside the upload request. Fine
  for the small CSVs used in testing; will not hold up against the
  "tens of thousands of properties" performance requirement (spec §72)
  until it moves to `worker/jobs/ingestion.py` behind a real RQ+Redis
  queue — architecture/02 §2 explains why this matters.
- **XLSX/XLS upload isn't supported**, only CSV — needs a real parsing
  library (openpyxl/Polars), deferred rather than half-wired.
- **Data Health v1 only checks Property fields.** The full spec §42 list
  (missing building relationships, duplicate components, missing
  handover information, orphan components, ...) needs the domain models
  those checks are about — added the same way, one function each, as
  Sprint 6+ lands them.

- **RLS is unverified against real Postgres.** The policy SQL in
  `alembic/versions/0001_foundation.py` and `0002_billing.py` is written
  correctly per the architecture but has never actually run against a
  live database. Treat tenant isolation as *unconfirmed* until the
  security tests in architecture/09 §2 exist and pass against Postgres.
- **Stripe is not wired up.** `StripeBillingProvider` doesn't exist yet;
  `STRIPE_SECRET_KEY` must be set and that class implemented before
  checkout/portal/webhooks do anything real. See
  `app/integrations/billing_provider.py`.
- **There's no membership-invite flow.** Signup creates exactly one
  OWNER; there's no way yet for an OWNER to add a second person to their
  org with a chosen role. The Sprint 2 billing-permission test
  (`test_viewer_cannot_start_checkout`) has to create that membership
  directly via the DB session because no API for it exists.
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
- Full browser click-through without Docker/Postgres/Redis: point
  `DATABASE_URL` at a local SQLite file and monkeypatch `redis_client` in
  `app.core.tenancy` / `app.auth.router` with an in-process fake before
  starting uvicorn — `app.tests.conftest.py`'s fixture is the reference
  implementation of both. Import `app.main` (not just `app.core.db`)
  before calling `Base.metadata.create_all(engine)`, or the model modules
  never register their tables and `create_all` silently does nothing —
  this bit the first version of the throwaway script used to verify
  Sprint 2 end-to-end.
