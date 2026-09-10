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

**Sprint 7 — Identifiers & Asset Coding:**

- `app/identifiers/`: the real Reference & Identifier Engine, replacing
  the `COUNT`-based generators every sprint since Sprint 4 flagged as
  interim. `generate_reference` reserves a sequence number under a row
  lock (`SELECT ... FOR UPDATE` on a per-org-per-entity-type
  `ReferencePattern` row) in the same transaction as the entity insert —
  two concurrent creates can no longer read the same number. Default
  patterns render to the **exact same strings** the old generators
  produced (`PROP-000001`, `DEV-000001`, ...) — proven by a test
  (`test_generate_reference_matches_the_pre_sprint_7_format`) — so this
  is a genuine non-breaking upgrade: the concurrency guarantee and
  configurability are new, the output format isn't churned for its own
  sake. Patterns are org-configurable via `PATCH
  /api/v1/reference-patterns/{entity_type}` (owner/admin only), verified
  live in-browser: changed the Properties pattern to
  `NORTHSTAR-{sequence:04d}` and the next property created picked it up
  immediately, continuing the existing sequence number, while the
  earlier property kept its original reference untouched.
- **The external reference model, with its hard write-path constraint,
  now actually exists** — `app.identifiers.models.ExternalReference`,
  not the plain nullable columns Sprints 5-6 used as an honest interim
  (`Property.uprn`, `Development.{planning_reference,
  building_control_reference, bsr_reference}`,
  `Building.{building_control_reference, bsr_reference}` — all removed
  by this sprint's migration). The constraint is enforced two ways, not
  just one: `record_external_reference` is the only function in the
  codebase that writes this table and refuses `SYSTEM_GENERATED` at the
  Python level, *and* a DB `CHECK` constraint refuses it independently —
  tested by inserting a bad row directly via the ORM, bypassing the
  service function entirely, and confirming Postgres-compatible SQLite
  still rejects it with an `IntegrityError`. Same two-layer-defence
  pattern as tenant isolation (RLS + app-layer scoping, Sprint 1).
- The API contract for `PropertyOut`/`DevelopmentOut`/`BuildingOut` is
  **unchanged** — `uprn`, `planning_reference`, etc. still appear in the
  JSON exactly as before, just resolved via a lookup
  (`app/development/presenters.py`) instead of a direct column read, so
  no frontend changes were needed for existing pages. List endpoints use
  a bulk lookup (one query for N entities), not one query per row.
- `apps/web`: new `/organisation` page (previously a bare stub) — a
  reference-pattern editor, the first real settings UI in the app.
- 13 new backend tests (80 total passing). Found and fixed one real bug
  along the way: `app/data_health/rules.py`'s `check_missing_uprn` still
  read `Property.uprn` directly — a column that no longer exists after
  this sprint's migration — caught immediately by the existing Sprint 5
  data-health test suite (not new hand-testing this time; the old tests
  did their job).

**Sprint 8 — Component Register:**

- `app/development/`: `Component` and `ComponentType` models — spec §22.
  `ComponentType` reuses the same global+org-specific catalog pattern as
  system roles (Sprint 1) and Plans (Sprint 2): 23 types seeded with
  `organisation_id = NULL` (visible to every org), and an org can add its
  own custom types on top (`organisation_id` set), auto-created during
  CSV import when a row's type name doesn't match anything seeded. This
  needed a non-standard RLS policy on `component_types`
  (`organisation_id IS NULL OR ...`) — the standard tenant-isolation
  policy used everywhere else would hide the global seeded rows the
  moment a tenant context is set, which would have made the catalog
  invisible to every org.
- `Component` attaches to a development, building, property, space,
  and/or a parent component — each attachment point is validated
  independently (existence only), not cross-validated against each
  other like `resolve_property_hierarchy` does for properties. Serial
  number is stored as an external reference
  (`ExternalReferenceType.MANUFACTURER_SERIAL_NUMBER`, Sprint 7's
  engine), not a plain column, matching the UPRN/planning-reference
  pattern. `indicative_replacement_date` is computed once at write time
  from `installation_date + expected_life_years` and is explicitly
  labelled "(indicative only)" in the UI — it's a planning aid, not a
  determination.
- References use Sprint 7's engine (`COMP-000001`, ...) — no interim
  generator was ever built for components, so this sprint went straight
  to the real thing.
- `apps/web`: `/components` (list + add form, component-type dropdown
  populated from the real seeded catalog) and `/components/[id]`
  (detail view + child-component list/add, exercising the parent/child
  hierarchy).
- CSV import (`app/development/importers.py`, registering `"COMPONENTS"`
  into the Sprint 3 pipeline) — the second real importer after
  Properties (Sprint 5), closing the "honest no-op" gap
  `test_ingestion.py` had used `COMPONENTS` to demonstrate since Sprint
  5. Unmatched type names auto-create an org-specific custom type rather
  than failing the row.
- 11 new backend tests (91 total passing). Two real bugs found and fixed
  by the test suite before this ever reached the browser: (1) type
  matching was exact-string-only, so a CSV using "Boiler" against the
  seeded "Boilers" created a needless duplicate custom type instead of
  matching — fixed with a naive singular/plural fallback
  (`_singularish`) in `find_component_type_by_name`; (2) the import path
  matched against the catalog before ever seeding it, so on a fresh org
  *nothing* matched and everything became a spurious custom type — fixed
  by calling `ensure_component_type_catalog_seeded` first in
  `import_component_row`.
- Verified end-to-end live: signed up a fresh org, added a component
  manually via the UI (`COMP-000001`, Boilers, Worcester Bosch/Greenstar
  8000), added a child component under it (`COMP-000002`) and confirmed
  the parent/child UI, then drove the CSV import path over real HTTP
  with `curl` (upload → mapping → import) using a row with the singular
  "Boiler" and a genuinely novel type name. Confirmed via
  `GET /api/v1/components` and `/component-types` that "Boiler" matched
  the existing global "Boilers" type (same `component_type_id` as the
  manual entry, no duplicate) while the novel type auto-created a new
  org-scoped `ComponentType`, and that references continued the same
  sequence (`COMP-000003`, `COMP-000004`) with correct provenance
  (`FILE_UPLOAD` vs `MANUAL`, `source_dataset_id`).

**Sprint 9 — Specifications / Documents / Golden Thread:**

- `app/development/`: `Specification` model — spec §27. Attaches to a
  development, building, property, space, or component via a plain
  polymorphic (`related_entity_type`, `related_entity_id`) pair, same
  pattern as `Document` rather than five nullable FK columns, since
  exactly one of the five is ever set for a given specification. Versions
  use Document's exact append-only pattern: a new revision is a new row
  sharing `lineage_id` and `specification_reference` with the first
  version, and the prior row is only ever marked `SUPERSEDED` (with
  `superseded_date` set), never edited in place — spec §26: "A change
  must NOT simply overwrite the previous specification." Approving a
  specification (`approved_by`/`approved_at`) does not carry forward to
  a new revision — a changed specification is unapproved again until
  someone approves the new text, confirmed live (see below).
  `related_entity_type` is validated against the five spec-named types
  (`UnsupportedEntityTypeError` → 400), unlike Document's genuinely
  open-ended field.
- **Golden Thread** (`app/development/golden_thread.py`) — spec §29,
  built exactly as architecture 03 §4 specifies: "not a new table — a
  read-composition across existing tables, expressed as one service
  function." `GET /api/v1/buildings/{id}/golden-thread` composes, for a
  building and every component attached to it (directly, or via a
  property under that building): current specifications, evidence
  (`Document` rows), external references/approvals (Sprint 7's engine),
  and a responsible party derived from provenance (creator, source type)
  plus any `CONTRACTOR_REFERENCE` external reference — no new
  responsible-party table needed, since provenance and external
  references already carry that information. Three links from spec §29's
  full chain have no canonical table yet — inspection (Sprint 16), change
  control (Sprint 10), handover (Sprint 12) — the response names them
  explicitly in `not_yet_available` rather than silently omitting them,
  and both the API and UI carry spec §29's explicit constraint that
  storing this information does not by itself satisfy every legal Golden
  Thread obligation.
- `apps/web`: no new nav item or standalone register page — a
  specification is something you look at *in the context of* the
  building or component it belongs to, so "Add a specification" +
  "Specifications" (list, status, approve) were added directly to the
  existing Building and Component detail pages, and "Golden Thread" as a
  new read-only section on the Building detail page. This also avoided
  needing an org-wide "list all spaces" endpoint that doesn't exist yet
  (Space is a valid attachment type at the API level, just not
  surfaced in either detail page's quick-add form).
- 13 new backend tests (104 total passing) — no bugs found by the suite
  this sprint (Sprint 9 didn't have Sprint 8's kind of matching-logic
  surface area to get wrong); the migration's DDL was checked with
  `alembic upgrade head --sql` (offline mode, no live Postgres needed)
  and confirmed `specificationstatus` is created once and the shared
  `sourcetype` enum is reused, not re-declared, continuing the check
  from Sprint 6.
- Verified end-to-end live: added and approved a building-level
  specification (`SPEC-000001`) through the UI, added a component to
  that building and a component-level specification through the UI,
  then over real HTTP with `curl`: uploaded evidence linked to the
  component, confirmed it appeared in the Golden Thread response
  alongside the component's specification and its `responsible_party`
  resolved to the signed-up user, and created a revision (`rev B`) of
  the building specification — confirming the prior revision flipped to
  `SUPERSEDED` with `superseded_date` set, the reference stayed
  `SPEC-000001` across both rows, and the new revision's `approved_by`
  came back `null` even though the revision it superseded had been
  approved.

**Sprint 10 — Construction Evidence / Change Control:**

- **Construction Evidence** (spec §32) needed no new table: architecture
  03 §7 describes it as documents linked "via a polymorphic
  (related_entity_type, related_entity_id) pair down to component/space
  granularity" — exactly the mechanism `Document` (Sprint 4) already has
  and Sprint 9's Golden Thread already surfaces read-only as
  `evidence`. Sprint 10's actual work here was closing the write-side
  gap: the Golden Thread evidence section was read-only, so this sprint
  is what a real user would use to put evidence there in the first
  place — verified by uploading a component-scoped document over curl
  (Browser pane tools can't drive a native file picker, same limitation
  noted since Sprint 3) and confirming it appears in both the component
  page and the building's Golden Thread.
- **Change Control** (spec §33): `ChangeControl` — a real six-state
  workflow (`PROPOSED → UNDER_REVIEW → APPROVED → IMPLEMENTED`, plus
  `REJECTED`/`CANCELLED`), not just a status column. Deliberately
  deviates from BUILD_PROMPT.md §33's literal sketch in one place: that
  sketch gives change_control its own
  development_id/building_id/property_id/component_id columns, but the
  doc explicitly calls these "Conceptual fields," and duplicating
  Specification's own polymorphic location alongside a `specification_id`
  FK would let the two drift out of sync. Every change instead targets
  exactly one `specification_id`, with `related_entity_type`/
  `related_entity_id` copied from it at submission time (immutable,
  for filtering without a join) — same "compose, don't duplicate"
  reasoning Sprint 9 used for Golden Thread, applied to a write path
  this time.
  `previous_value` is captured automatically from the specification's
  live fields at submission — never accepted from the caller — so it
  stays trustworthy regardless of what happens to the specification
  afterwards. Approving and implementing are two separate actions
  (approving records a decision; implementing is what actually calls
  Sprint 9's `create_specification_revision`, superseding the old
  specification row and recording which new row resulted) — a real
  workflow can approve now and implement at a scheduled cutover later,
  which is why the spec gives six statuses instead of a simpler
  approve-and-done model.
  `external_approval_reference` (an optional field on approval) routes
  through Sprint 7's `ExternalReference` engine with a new
  `EXTERNAL_APPROVAL_REFERENCE` type, not a plain column — same
  hard-write-path reasoning as every other official external identifier
  in this codebase.
- **Golden Thread updated**: the CHANGE link in spec §29's chain is now
  real (`ChangeControl` rows matched by the same related_entity_type/id
  every other Golden Thread link uses, so a change stays visible in a
  location's history even once implemented and the specification it
  targeted has been superseded). `not_yet_available` now lists only
  `inspections` (Sprint 16) and `handover_records` (Sprint 12).
- `apps/web`: Change Control surfaces on the Component detail page next
  to Specifications — propose a change against any current specification,
  and status-appropriate action buttons (Start review / Approve / Reject
  / Cancel / Implement) per row. The Building page's Golden Thread
  section shows each component's change history alongside its
  specifications and evidence.
- 20 new backend tests (114 total passing). One real bug found during
  browser verification (not by pytest — this one needed the actual UI):
  the Component page's "Change control" list was filtered by the
  *specification's* id, so a change disappeared from the page the moment
  it was implemented (implementing supersedes the old specification row,
  and the change stays permanently linked to that now-superseded row's
  id). Fixed by filtering the list query by the *component's*
  related_entity_type/related_entity_id instead — stable across the
  specification's whole revision lineage — confirmed live: an
  implemented change (`CHG-000001`) now stays visible with its terminal
  `IMPLEMENTED` badge on both the component page and the building's
  Golden Thread.
- Verified end-to-end live: added a building specification and a
  component specification through the UI; submitted a change against
  the component specification over curl (confirming the automatic
  `previous_value` snapshot matched the specification's actual fields);
  drove the full `start-review → approve → implement` sequence through
  the real UI buttons, confirming at each step the specification list
  showed the new revision (`rev B`) with the old one gone from the
  current-only view, and confirmed a separate change's `reject` path and
  the `approve`-after-`reject` 400 guard over curl.

**Sprint 11 — Defects / Warranties:**

- `app/development/`: `Defect` (spec §34) attaches like `Component` —
  independent, non-cross-validated development/building/property/
  component FKs — rather than Specification's single polymorphic pair,
  since a defect genuinely can be reported at whichever level it was
  actually observed at. A real seven-state workflow (`OPEN → ASSIGNED →
  IN_PROGRESS → READY_FOR_INSPECTION → COMPLETED → CLOSED`, plus
  `REJECTED`, and a failed inspection routes back to `IN_PROGRESS`
  rather than forcing a new defect for the same snag) — validated
  transitions, same rigor as Change Control's status machine (Sprint
  10). `estimated_cost_pence`/`actual_cost_pence` are integers, never
  floats — same reasoning as Plan pricing
  (`app/platform/billing.py`). The spec's `evidence` field isn't a
  column: photos/reports attach the same way Construction Evidence does
  (Sprint 10), a `Document` with `related_entity_type="defect"`.
- `Warranty` (spec §36): same independent multi-attachment shape as
  Defect. Status only ever tracks `ACTIVE`/`VOID`, set by an explicit
  action (`void_warranty`) — "EXPIRED" is deliberately never a stored
  status a background job would have to keep in sync. `is_expired` and
  `days_until_expiry` are computed from `expiry_date` at read time
  instead, same "deterministic, computed at read time" approach as
  Component's `indicative_replacement_date` and Data Health's score.
  "Generate configurable alerts before expiry" (spec §36) is served by
  `GET /api/v1/warranties?expiring_within_days=N` — the caller/UI
  controls the window; there's no email/notification infrastructure in
  this codebase to push an alert through, same honest-scoping reasoning
  as `StripeBillingProvider` staying deferred since Sprint 2.
- **Defects Intelligence** (spec §35, `app/development/
  defects_intelligence.py`): a fixed set of aggregate reads — open/
  overdue/warranty-related counts, by-contractor, by-category, by-
  component-type, repeat-category detection (a category counts as
  "repeat" when it recurs at the *same* property/building/component,
  matching spec §35's own example: "7 properties have repeat
  water-ingress defects"), total cost, average resolution time — every
  number directly re-derivable from `GET /api/v1/defects`. Deliberately
  not a scored/weighted registry like Data Health (Sprint 5) or
  Component Lifecycle: the spec's own examples are plain counts, so
  that's what this composes.
- `apps/web`: "Report a defect"/"Defects" and "Add a warranty"/
  "Warranties" sections added to the Building detail page, next to
  Specifications/Change Control/Golden Thread — no new nav item, same
  reasoning as Sprint 9/10 (these are naturally viewed in the context of
  the building they belong to, and Build 1's nav config has no slot
  reserved for them). Defect status transition buttons are generated
  from the same allowed-next-states the backend enforces, so the UI
  never offers a transition the API would reject.
- 17 new backend tests (131 total passing) — no bugs found by the test
  suite; migration DDL checked offline (both new enums created once,
  `sourcetype` reused rather than re-declared, continuing the check from
  Sprints 6 and 9-10).
- Verified end-to-end live: reported a defect against a building through
  the UI (`DEF-000001`), drove it through
  `ASSIGNED → IN_PROGRESS → READY_FOR_INSPECTION → COMPLETED` (confirming
  `completion_date` defaulted correctly and `actual_cost_pence` was
  recorded) and confirmed the UI only ever offered the buttons the
  backend's transition table allows; added a warranty (`WAR-000001`)
  through the UI and confirmed `days_until_expiry` renders live, then
  voided it and confirmed the terminal `VOID` badge with the action
  removed; confirmed `GET /api/v1/defects/intelligence` matched the
  actual defect over curl, and that `expiring_within_days` correctly
  excluded a warranty over a decade from expiry.

**Sprint 12 — Handover & Operational Transition:**

- **Handover Readiness Engine** (`app/development/handover.py`, spec
  §37) — a registry of nine independent, weighted checks, same shape as
  Data Health's rule registry (Sprint 5) but weighted and per-org
  configurable (`HandoverReadinessCheckWeight`, lazily seeded exactly
  like Sprint 7's `ReferencePattern`), because spec §37 calls scoring
  configurability out as core to this engine specifically, not a later
  enhancement the way Data Health's weighting stayed. Ten checks are
  named in spec §37's own list; nine are real registry entries —
  "Outstanding remedial actions" has no table to check yet (that's
  Compliance Operations, Sprint 16) and isn't faked as an always-passing
  check, so the other checks' weights are renormalised to still sum to
  100%. "Missing evidence" and "Data-quality problems" from the same
  list aren't separate checks either — checks 3-6 (component fields,
  warranties, certificates, commissioning evidence) and the existing
  Data Health module already cover that ground.
  A development with **zero properties recorded scores 0%, not a
  vacuous ~85%** — `HandoverCheckResult.pass_ratio` is `1.0` when
  `applicable_count` is 0 (correct once real properties/components
  exist and a given check genuinely has nothing to apply to), and this
  was caught by this sprint's own test (not a spec requirement written
  down anywhere, but an obvious correctness bug once the test made the
  number concrete).
- **Handover workflow** (`app/development/service.py.authorise_handover`,
  spec §9/§38) — exactly the transaction the architecture describes:
  assert readiness meets the threshold (or an explicit `override_reason`
  from a `development.handover`-permitted role — `HANDOVER_MANAGER`,
  the permission Sprint 1 created and this sprint is the first to
  actually gate anything behind), flip every in-scope
  `READY_FOR_HANDOVER` property to `HANDED_OVER` in one transaction,
  write one `HandoverRecord` per property capturing the full readiness
  snapshot (not just the headline score), audit each. Properties not
  currently `READY_FOR_HANDOVER` are left untouched, so a development
  can be handed over in phases. Threshold is fixed at 100% for v1 — spec
  §37 only calls out the *scoring methodology* as needing to be
  configurable, not the pass/fail bar, and the override path already
  covers the real "ships below 100% for a documented reason" case.
  `PropertyStatus.HANDED_OVER` can only be reached through this action —
  the new `POST /api/v1/properties/{id}/status` endpoint (for the
  ordinary `PLANNED → UNDER_CONSTRUCTION → READY_FOR_HANDOVER`
  progression) explicitly refuses to set it directly.
- Preserving development history at handover needed **no new code at
  all** — architecture 03 §9 already decided this back when Component/
  Specification/Warranty/Defect were built: handover is a status flip
  on the same `properties` rows, never a copy, so the component
  register, specifications, evidence, warranties, defects and Golden
  Thread composition are automatically unchanged by the flip (spec §39).
- `apps/web`: "Handover readiness" + "Handover history" sections added
  to the Development detail page (score, missing items, override-reason
  field, authorise button); a "Change status" control added to the
  Property detail page for the ordinary pre-handover progression, with
  `HANDED_OVER` deliberately absent from its options.
- 12 new backend tests (143 total passing). One real bug found by the
  test suite itself before this ever reached the browser: an empty
  development (no properties) scored ~85% instead of 0%, because eight
  of the nine checks have nothing to apply to yet and vacuously "pass" —
  fixed by special-casing zero properties to a flat 0% rather than
  letting the weighted average paper over "nothing has been captured."
- Verified end-to-end live: built a development with a building
  (Building Control reference), a property, and a component carrying a
  warranty, an electrical certificate, a commissioning record and a
  development-level O&M document — confirmed the readiness score moved
  from 78.9% (missing components-captured and O&M items, matching
  exactly) to 100% as each piece was added over curl; set the property
  to `READY_FOR_HANDOVER` through the new UI control and authorised
  handover through the real UI button, confirming the property flipped
  to `HANDED_OVER` and the full 9-check readiness snapshot was recorded
  permanently in `handover_records`; confirmed the weight-configuration
  PATCH endpoint and its 404 guard on an unknown check_code over curl.

**Sprint 13 — Property 360 / Portfolio:**

- **Refactored before extending**: Golden Thread's per-component bundle
  (specs/evidence/changes/responsible party/external references) was
  duplicated logic Property 360 needed identically, just gathered by
  property instead of by building — pulled out into
  `app/development/composition.py` (`build_component_view` and the
  entity-agnostic `current_specifications`/`evidence_for`/`changes_for`
  helpers) so both views call the same functions instead of copying
  them. Caught and fixed a real gap while touching this code: Golden
  Thread's `not_yet_available` still listed "handover (Sprint 12)" after
  Sprint 12 shipped and never actually wired in `HandoverRecord` data —
  fixed by adding a real `handover_records` field (properties under the
  building, same as every other Golden Thread link) rather than just
  deleting the stale list entry.
- **Property 360** (`app/development/property_360.py`, spec §41) — a
  read-composition exactly like Golden Thread and Handover Readiness,
  scoped to one property: property info, development/building/floor
  history, the same per-component bundle Golden Thread uses (including
  components attached via a space, not just directly), property-level
  specifications/evidence/change control, warranties and defects (both
  property- and component-level), the property's handover record if
  any, Data Health findings filtered to this property (reusing the
  existing Sprint 5 rule registry, not a duplicate one), and a Timeline
  — the first real consumer of `AuditEvent` reads in this codebase,
  composed from `entity_type IN ("property", "component")` rows every
  service function since Sprint 5 has already been writing. Repairs,
  Compliance & Safety, Stock Condition/Planned Investment, Tenancy/
  Lease, Rent & Payments, Attention Signals and Ask DataLume have no
  canonical data yet — named explicitly in `not_yet_available`, same
  honesty pattern as Golden Thread's own list.
- **Portfolio rollups** (`app/development/portfolio.py`) — an org-wide
  counterpart to Property 360: total properties/developments/buildings/
  components, properties by status, the org's Data Health score, open/
  overdue defect counts, warranties expiring within 90 days, and each
  development's current handover readiness score. Every number is a
  direct read over tables that already exist — nothing new is stored.
  This replaces the Home dashboard's ad-hoc client-side property-count-
  plus-data-health fetch (present since Sprint 5) with one real
  backend-computed endpoint.
- `apps/web`: the Property detail page is now genuinely the Property
  360 view (components, warranties, defects, Data Health, timeline, not-
  yet-available footer, all in one place); Home now shows six real KPIs
  plus a properties-by-status breakdown and a per-development handover
  readiness list, sourced from the one new portfolio endpoint instead of
  two ad-hoc calls.
- 8 new backend tests (152 total passing) — no bugs found by the suite;
  the two real issues this sprint caught (Golden Thread's stale
  not_yet_available entry, and the shared composition logic that
  motivated the refactor) were both found by re-reading the code while
  extending it, not by a failing assertion.
- Verified end-to-end live: built a development with two properties, a
  component, a warranty and an overdue defect over curl and confirmed
  Home's KPIs matched exactly (2 properties, 1 development, 1 component,
  correct status breakdown, 1 open defect, correct development
  readiness %); opened the enriched property page and confirmed every
  section composed correctly (development → building breadcrumb,
  component with its own specs/evidence/changes, warranty days-
  remaining, defect severity/status, Data Health findings scoped to
  just this property, a timeline with real actor names and timestamps);
  authorised handover for that property and confirmed both the property
  page's Handover field and Timeline updated correctly, and that the
  building's Golden Thread now shows the same handover record with its
  full readiness snapshot.

**Sprint 14 — Repairs / Component Failures:**

- **New domain package**: `app/operations/` — the first module outside
  `app.development`, matching architecture/04's own document boundary
  from architecture/03. Gated by the `operations.read`/`operations.write`
  RBAC permissions that have existed since Sprint 1 (REPAIRS_MANAGER,
  PROPERTY_MANAGER, ASSET_MANAGER) but had nothing to gate until now —
  the same "give an old permission its first real use" pattern as
  Sprint 12's `development.handover`.
- `Repair` (architecture/04-operations-domain.md §1) — `property_id` is
  required (unlike `Defect`'s fully-optional multi-attachment): a repair
  is inherently a post-handover, day-to-day operational concern tied to
  one property, not something reported against a development-phase
  location that doesn't exist yet. `contractor` stays a plain string,
  not a `contractor_id` FK — no Contractor domain exists anywhere in
  this build, same precedent `Defect.contractor` already set in Sprint
  11. `is_emergency` is derived from `priority == EMERGENCY` at write
  time rather than accepted as an independent input, so the two columns
  the spec's SQL sketch lists separately can never disagree.
- **Repeat Repair / Component Failure engine**
  (`app/operations/repeat_repair.py`, spec §44: "do not let the LLM
  invent calculations") — three independent, separately testable
  functions (`repeat_repairs_for_property`, `repeat_failures_for_component`,
  `component_model_trend`), each returning `None` rather than a
  zeroed-out signal when the pattern isn't met. `window_months`/
  `threshold`/`threshold_ratio`/`min_installed_base` are per-organisation
  configurable via `RepairRuleConfig` (lazily seeded, same pattern as
  Sprint 7's `ReferencePattern` and Sprint 12's
  `HandoverReadinessCheckWeight`) rather than hard-coded — confirmed
  live that raising a threshold immediately silences a previously-
  triggered signal, with no code change. Every signal carries its own
  `repair_ids`/`window`/`threshold` inputs, computed fresh on every
  read rather than persisted — same "deterministic, computed at read
  time" approach as Data Health and Handover Readiness, so there's
  nothing to go stale between writes.
- **Repairs Intelligence** (spec §43) — a fixed set of aggregate reads
  (open/completed/emergency counts, by-category, by-contractor, total
  cost, average completion time), folding in every currently-triggered
  repeat-repair/component-failure signal — same "not a scored engine"
  reasoning as Defects Intelligence (Sprint 11).
- **Property 360 updated**: repairs are now wired in for real — `repairs`
  field added, `not_yet_available` no longer lists them, and the
  Timeline now also covers `repair.*` audit events alongside
  `property.*`/`component.*`. Caught while doing this: the exact same
  "stale not_yet_available entry" pattern Sprint 13 fixed for Golden
  Thread's handover link — fixed the same way, by wiring in real data
  rather than just deleting the list entry.
- `apps/web`: `/repairs` is now a real page (KPIs, repeat-repair pattern
  list, report-a-repair form, register with status-transition buttons)
  replacing the `ComingSoon` stub that had been there since Sprint 1;
  the Property detail page gained its own Repairs section.
- 14 new backend tests (166 total passing) — one test-authoring mistake
  caught by the suite itself before anything else did (a model-trend
  test asserted a signal would trigger with a failure ratio below the
  threshold it had just configured — fixed the test's own arithmetic,
  not the engine).
- Verified end-to-end live: reported a repair through the real UI and
  drove it through `SCHEDULED`; created three more repairs against the
  same property/component over curl and confirmed both repeat-repair
  signals (property-level and component-level) appeared on the Repairs
  page with the exact counts and thresholds; confirmed the same repairs
  composed correctly into Property 360 (list, timeline); confirmed live
  that raising `REPEAT_REPAIRS_PER_PROPERTY`'s threshold via the config
  endpoint immediately silenced the signal for the same underlying data.

**Sprint 15 — Compliance Foundation:**

- **New domain package**: `app/operations/compliance/` (models, seed,
  schemas, service, router) — a subpackage of `app.operations` rather
  than a flat file like Repairs (Sprint 14), since Compliance spans
  three sprints (Foundation/Operations/Assurance, per
  architecture/04-operations-domain.md §3 and spec §45-46) and has more
  surface area. This sprint builds only the first four links in the
  spec's chain — FRAMEWORK → DOMAIN → REQUIREMENT → APPLICABILITY —
  explicitly *not* INSPECTION/ACTION (Sprint 16) or the STATUS engine
  (Sprint 17), per the roadmap's own split.
- **Global+org-specific catalog pattern reused**: `organisation_id` is
  nullable on `ComplianceFramework`/`ComplianceDomain`/
  `ComplianceRequirement` — `NULL` means a DataLume-seeded global
  default visible to every org, non-`NULL` means one org's own
  addition. Same shape as `ComponentType` (Sprint 8), and it needs the
  same non-standard RLS policy (`organisation_id IS NULL OR
  organisation_id IS NOT DISTINCT FROM ...`) rather than the standard
  tenant-isolation policy — captured in the migration's
  `_global_or_org_rls()` helper.
- **Only the 21 domain names are seeded, deliberately** — a stable
  taxonomy spec §45 names explicitly. No default requirement content
  (title/cadence/obligation text) is pre-populated, because fabricating
  plausible-sounding regulatory obligations would be exactly the kind
  of AI-invented compliance interpretation spec §31/§47 warns against.
  Orgs add their own requirements under any domain, global or custom.
- **Requirement versioning without a `lineage_id` column**: unlike
  `Specification`/`Document` (explicit `lineage_id`), a requirement's
  versions are grouped by `(domain_id, code)` as the natural lineage
  key — `code` is meant to be a stable regulatory identifier. A new
  version is a new row with `version` incremented; the prior row only
  ever gets `superseded_date` set, never edited in place — same
  append-only pattern as `Specification` (Sprint 9).
- **`operations.compliance` permission's first real use** — narrower
  than `operations.write`, held only by COMPLIANCE_MANAGER and
  BUILDING_SAFETY_MANAGER in RBAC (not REPAIRS_MANAGER/PROPERTY_MANAGER,
  who run day-to-day repairs but shouldn't reshape the compliance
  framework itself). Defined back in Sprint 1; this is the first sprint
  that gates anything with it.
- **Applicability** (`RequirementApplicability`) links a requirement to
  a building, property, or component — strictly those three entity
  types (spec's own chain), not "development". Standard tenant RLS
  (not the global/org-nullable variant), since an applicability record
  is always one org's own decision about its own stock.
- **Bug found and fixed during live verification**: `create_requirement`
  had no guard against two independent requirements sharing a
  `(domain_id, code)` while both current (non-superseded) — which
  would silently corrupt the `(domain_id, code)`-based version-lineage
  lookup used by `create_requirement_version` and the requirement
  detail endpoint's version list. Found by accident: a UI click landed
  on the wrong domain (see below), which meant creating the *right*
  requirement afterwards required creating it a second time, and
  nothing stopped that duplicate from being accepted. Fixed with a new
  `DuplicateRequirementCodeError`, a pre-insert existence check scoped
  to `(organisation_id, domain_id, code, superseded_date IS NULL)`, and
  a regression test confirming the same code is still allowed across
  *different* domains (codes are scoped to domain, not global). Full
  suite re-run: 181 passed.
- `apps/web`: `/compliance` is now a real two-panel page (domain list +
  requirements for the selected domain, "Add a domain" / "Add a
  requirement" forms, `(custom)` tag on org-specific domains) replacing
  the `ComingSoon` stub. The Building detail page gained an "Add a
  compliance requirement" form and a Compliance requirements list
  (Applicable/Ended badge, End action) alongside its existing sections.
- 15 new backend tests (181 total passing): seeded catalog (21 domains,
  all global), seeded framework, org-specific domain creation,
  requirement create/version/supersede, applicability create/end/
  list-filter, permission checks (REPAIRS_MANAGER lacks
  `operations.compliance`), cross-org 404s, and the duplicate-code
  regression above.
- Verified end-to-end live against the SQLite+fake-Redis smoketest
  server: signed up, confirmed all 21 global domains render on
  `/compliance`, added a `GAS-001` requirement under Gas Safety through
  the real UI. During that pass, a browser-automation click landed on
  the wrong domain button (a recurring `computer`-tool click
  reliability issue in this environment — switched to a JS-driven click
  via `javascript_tool`, which worked), which is what surfaced the
  duplicate-code gap above. After the fix, killed and restarted the
  smoketest server (service-layer code changes need a restart — this
  script has no `--reload`), re-signed-up fresh, and confirmed via curl
  that a duplicate `GAS-001` create now correctly returns `400` while
  the first create still returns `201`. Re-loaded `/compliance` in the
  browser against the fresh, code-current server and confirmed all 21
  domains and the requirements panel still render correctly.

**Sprint 16 — Compliance Operations / Safety / Hazards:**

- **Compliance Operations extends Sprint 15's chain**: `Inspection` and
  `ComplianceAction` (`app/operations/compliance/models.py`) add the
  INSPECTION -> EVIDENCE -> ACTION -> DEADLINE links, closing the gap
  the module's own docstring named as Sprint 16's job. `Inspection`
  carries a generic SATISFACTORY/UNSATISFACTORY/ADVISORY `result` — a
  common UK-certification shape (e.g. a Gas Safety Certificate), not a
  claim about any one scheme's own terminology. `ComplianceAction` can
  arise from an inspection (`inspection_id` set) or be raised
  independently, with its own OPEN/COMPLETED/CANCELLED transition
  guard (same enforced-dict pattern as Repair/Defect status machines).
  `evidence_document_id` on both is a plain FK to an already-uploaded
  Document (upload separately via `POST /documents`, then reference its
  id) — no bespoke inline upload endpoint.
- **New `app/operations/hazards/` subpackage** for Hazards, damp &
  mould (architecture/04 §5, spec §49). Damp & mould is a `hazard_type`
  *value* on one `Hazard` table, not a parallel schema — `hazard_type`
  is free text (e.g. `DAMP_AND_MOULD`, `EXCESS_COLD`), the same
  non-fabrication stance Sprint 15 took with requirement content:
  HHSRS's 29 official hazard categories are a real regulatory taxonomy
  this build has no authoritative source to hard-code as canonical.
- **`Hazard.status` state machine**: REPORTED → TRIAGED → INVESTIGATING
  → INVESTIGATED → ACTION_IN_PROGRESS → FOLLOW_UP → CLOSED (with
  FOLLOW_UP able to reopen into ACTION_IN_PROGRESS) — a coarse,
  enforced simplification of spec §49's full named chain
  ("...DEADLINE -> FINDING -> ACTION -> DEADLINE -> COMPLETION ->
  EVIDENCE -> FOLLOW-UP -> CLOSED"): the ACTION/DEADLINE/COMPLETION/
  EVIDENCE portion is carried by separate `HazardAction` rows instead
  of more `Hazard.status` values, mirroring how Compliance splits
  "what was found" (Inspection) from "what's being done about it"
  (ComplianceAction) onto two tables. `investigation_status`
  (PENDING/CONFIRMED/NOT_CONFIRMED/INCONCLUSIVE) is a separate field
  from `status` — the investigation's *outcome*, recorded once
  alongside `findings`, not another step in the same progression.
- **Repeat hazard-occurrence engine**
  (`app/operations/hazards/repeat_hazard.py`) reuses Sprint 14's
  repeat-signal pattern exactly (`HazardRuleConfig`, lazily seeded,
  per-organisation configurable window/threshold) but scoped by
  `(property, hazard_type)` rather than property alone — a repeat
  *pattern* is the same kind of hazard recurring, not any two
  unrelated hazards sharing an address. Confirmed live that raising
  the configured threshold immediately silences a previously-triggered
  signal, same as Sprint 14's repair engine.
- **`operations.compliance` permission reused for hazard writes**, not
  the broader `operations.write` — hazards (especially HHSRS-category
  ones) are the same safety-critical territory as the compliance
  framework, held by COMPLIANCE_MANAGER/BUILDING_SAFETY_MANAGER only.
- **Real gap found and fixed via live testing, unrelated to this
  sprint's own new tables**: Golden Thread's `not_yet_available` list
  has said `"inspections (Sprint 16)"` since Sprint 9 — a true claim
  until this sprint actually built the `Inspection` table, at which
  point it became a stale, false claim sitting in a view whose whole
  purpose is not overstating what's traceable. Caught by literally
  reading the Building detail page after wiring up compliance
  inspections. Fixed by composing `Inspection` rows into Golden
  Thread properly — both building-level and per-component (the same
  `evidence_for`/`changes_for` pattern in `app/development/
  composition.py`, now joined by `inspections_for`) — and clearing the
  list rather than leaving a placeholder. `GoldenThreadComponentOut`
  gained an `inspections` field, which Property 360 picks up for free
  since both composed views share `build_component_view`.
  `test_golden_thread.py` updated to assert the real composition
  instead of the stale claim.
- `apps/web`: `/safety` is now a real page (report-a-hazard form,
  register with state-machine transition buttons, an inline
  findings-recording form for the INVESTIGATING step, a hazard-actions
  panel, and repeat-hazard-pattern callouts) replacing the `ComingSoon`
  stub that named this exact sprint. The Building detail page's
  existing Compliance requirements section (Sprint 15) gained an
  inline inspections/actions panel per applicable requirement — record
  an inspection, see the latest result, raise and complete actions,
  all implicitly scoped to that building.
- 18 new backend tests (199 total passing): inspection recording and
  entity/requirement validation, action lifecycle and status-filtered
  listing, the full hazard state machine (happy path and an illegal
  skip), hazard action lifecycle, repeat-hazard triggering/threshold/
  hazard-type-isolation, permission checks, cross-org 404s — plus the
  Golden Thread test's assertions above.
- Verified end-to-end live: reported a `DAMP_AND_MOULD` hazard through
  the real `/safety` UI, drove it through every state (triaged →
  investigating → recorded findings via the inline form → investigated
  → action in progress), raised a hazard action, completed it, and
  confirmed the badges updated correctly at each step. Separately
  recorded a compliance inspection against a component through the
  Building detail page's new panel and confirmed it appeared correctly
  composed into that building's Golden Thread — which is what surfaced
  and let me fix the stale `not_yet_available` gap above.

**Sprint 17 — Compliance Assurance:**

- **`status_engine.py`**: `compliance_status(entity_type, entity_id, requirement)`
  implements architecture §4's pseudocode close to line-for-line —
  deterministic, computed fresh on every read from `Inspection`/
  `ComplianceAction`/`RequirementApplicability` rows, nothing persisted
  (spec §47: "AI may explain results but never invent status" — there
  is no write path into a status column because there is no status
  column). Same "computed at read time" philosophy as Data Health,
  Handover Readiness, and the repeat-signal engines threaded through
  every prior sprint.
- **Two ambiguous pseudocode signals, resolved and documented**: (1)
  the sketch names both `UNKNOWN` and `MISSING_EVIDENCE` for "latest
  inspection is None" but gives no second signal to distinguish
  them — this build reads it as a configurable grace period since
  applicability began (`ComplianceStatusConfig.never_assessed_grace_days`,
  default 30 days): within grace = too soon to expect evidence
  (`UNKNOWN`), past it = a genuine gap (`MISSING_EVIDENCE`). (2)
  `requires_review(latest)` is read as "last inspection result was
  UNSATISFACTORY/ADVISORY with no open action currently covering it."
  Both decisions are documented at the exact branch in
  `status_engine.py`, the same "make a defensible call, write down
  why" pattern as Sprint 15's 21-domains decision.
- **New `ComplianceRequirement.hard_deadline` column** (default
  `True`) — named directly in architecture §4's own pseudocode to
  branch `OVERDUE` (statutory, e.g. gas safety) vs `EXPIRED` (soft,
  e.g. an EPC re-rating nudge) once a next-due-date has passed.
  Carried forward on `POST .../versions` the same way `cadence` is.
- **All ten statuses implemented**: `NOT_APPLICABLE`, `UNKNOWN`,
  `MISSING_EVIDENCE`, `OVERDUE_ACTION`, `OPEN_ACTION`, `OVERDUE`,
  `EXPIRED`, `DUE_SOON`, `NEEDS_REVIEW`, `CURRENT` — each with its own
  isolated regression test.
- **`assurance.py`**: the Board Assurance report (spec item 57) is a
  read-only rollup — status counts grouped by domain, open/overdue
  action totals, hazard status/severity counts — over already-computed
  `compliance_status` values, never a scored or narrated summary of
  its own. Gated by the existing `reports.board` permission (EXECUTIVE/
  OWNER/ADMIN only — its first real use since Sprint 1). Optional
  `building_id`/`property_id` filters give the spec's "property vs
  portfolio" granularity; documented limitation: `Hazard` has no
  `building_id` column, so a `building_id` filter narrows the
  compliance side of the report but leaves the hazard section
  portfolio-wide rather than silently pretending to filter it.
- `apps/web`: the Building detail page's existing Compliance
  requirements section (Sprint 15/16) now shows the real computed
  status badge (colour-coded: green CURRENT, amber DUE_SOON/
  NEEDS_REVIEW/OPEN_ACTION/EXPIRED, red OVERDUE/OVERDUE_ACTION/
  MISSING_EVIDENCE) alongside the existing "Applicable" badge, and
  refreshes it immediately after recording an inspection or completing
  an action. `/compliance` gained a "Board Assurance" section — a
  status-count table grouped by domain plus open/overdue/hazard
  totals — that quietly renders nothing for a role without
  `reports.board` rather than erroring.
- 21 new backend tests (217 total passing): one isolated test per
  status branch, config-threshold-change tests (raising `due_soon_days`
  silences a `DUE_SOON` signal; lowering `never_assessed_grace_days`
  flips `UNKNOWN` to `MISSING_EVIDENCE` — same "config change, no code
  change" confirmation every prior engine sprint has made), the
  assurance report's domain/hazard rollup and its `property_id` hazard
  filter, and permission checks (`REPAIRS_MANAGER` denied on both
  status-config writes and the assurance report; `EXECUTIVE` allowed
  on the assurance report).
- Verified end-to-end live: walked a single requirement through
  `NOT_APPLICABLE` → `MISSING_EVIDENCE` → `DUE_SOON` via curl against a
  freshly-seeded org, confirming each transition matched the pseudocode
  exactly. Separately, through the real Building detail page UI,
  recorded an inspection and watched the status badge update live from
  `MISSING EVIDENCE` to `CURRENT` without a page reload (the
  `InspectionsPanel`'s `onChanged` callback triggering a
  `listComplianceStatuses` refetch). Confirmed the `/compliance` page's
  Board Assurance table renders the correct per-domain status count
  for the same org.

**Sprint 18 — Stock Condition / Planned Investment:**

- **New `app/operations/stock_condition/` subpackage**: `StockConditionSurvey`
  (architecture/04-operations-domain.md §6) — property-level periodic
  surveys with a free-form `condition_ratings` JSON map ({element:
  rating}), not a fixed set of columns or an assumed survey
  methodology. Feeds Data Health directly: two new checks
  (`MISSING_STOCK_CONDITION_SURVEY`, `STALE_STOCK_CONDITION_SURVEY`)
  registered in the existing rule registry (Sprint 5), closing
  architecture's own "feeds Data Health (missing/stale surveys)"
  instruction.
- **`app/development/planned_investment.py`**: `investment_priority`
  implements architecture §6's scoring pseudocode — five weighted,
  independently-explainable factors (spec §40: "do not use age
  alone"): AGE_RATIO, CONDITION_SIGNAL, REPAIR_FREQUENCY,
  FAILURE_PATTERN, COMPLIANCE_LINKED. Every factor's own value, weight,
  applicability, and a human-readable detail string is always returned,
  never folded silently into one number — same shape as Handover
  Readiness's checks (Sprint 12). A factor with nothing to go on (no
  installation date; no inspection ever recorded) is excluded from the
  weighted average rather than scored as a false pass, the same
  renormalisation Handover Readiness uses.
- **Deliberate deviation from the pseudocode's "nightly job + upsert"
  framing**: architecture's own sketch frames this as a scheduled
  `worker/jobs/component_lifecycle.py` job that persists a
  `planned_investment_signal` row. This build has no job/worker
  infrastructure — the roadmap's own Sprint 21 is explicitly where a
  "nightly scan job" first appears. Rather than build a job runner two
  sprints early for one engine, this follows every other scoring engine
  in the codebase (Data Health, Handover Readiness, repeat-repair/
  repeat-hazard, Sprint 17's compliance_status): computed fresh on
  every read, nothing persisted. Documented explicitly in
  `planned_investment.py`'s own docstring.
- **CONDITION_SIGNAL reuses Sprint 16's Inspection table** (component-
  level, any requirement) rather than trying to derive a per-component
  signal from `StockConditionSurvey.condition_ratings` — that JSONB
  blob has no documented mapping from its free-form element keys onto
  individual components, and inventing one would be exactly the kind
  of unfounded interpretation this codebase avoids elsewhere. The
  survey's real, documented job is feeding Data Health, not Planned
  Investment's per-component score — architecture's own words: "one
  more input signal, not a separate scoring system."
- **RBAC fix**: `ASSET_MANAGER` gained `operations.write` — the role
  this whole sprint's domain is named for previously had only
  `operations.read`, meaning it couldn't record the stock condition
  surveys that domain is actually about. A targeted, documented
  correction (regression-tested), not a broad autonomous change.
- `apps/web`: `/stock-condition` (survey register + record form) and
  `/planned-investment` (portfolio list ranked by score, expandable
  per-component factor breakdown, live-editable factor weights) replace
  their `ComingSoon` stubs. The Component detail page gained a Planned
  Investment section with the same expandable factor breakdown.
- 21 new backend tests (232 total passing): survey CRUD and its two
  Data Health checks, isolated tests per scoring factor (age-only,
  condition, repair frequency + failure pattern together, compliance-
  linked), a weight-change test confirming a raised weight increases
  its contribution, portfolio-list sorting/filtering, the
  ASSET_MANAGER RBAC fix, and permission checks. Two existing Data
  Health tests updated for the new checks' effect on their fixture
  properties (a property with no survey now genuinely has one more
  finding than before this sprint).
- Verified end-to-end live: via curl, created a boiler component aged
  exactly to its expected life (15/15 years) with no other signals and
  confirmed the returned score (46.6) matched hand-calculated weighted
  math exactly — `(0.35 × 0.999) / 0.75 × 100`. Through the real UI,
  recorded a stock condition survey on `/stock-condition` and watched
  it appear in the register with its condition rating; loaded a
  component aged 8/15 years on its own detail page and confirmed the
  same factor-by-factor breakdown rendered correctly, then confirmed
  the identical score appeared on the `/planned-investment` portfolio
  list.

**Sprint 19 — Tenancies / Commercial:**

- **New `app/commercial/` top-level package** — one per architecture-doc
  domain, mirroring `app.development` (~architecture/03) and
  `app.operations` (~architecture/04); this is `app.commercial`'s first
  sprint, covering architecture/05-commercial-domain.md §1's `Tenant`
  and `Lease` tables only. `rent_obligations`/`payment_transactions`/
  `payment_allocations` and the reconciliation/arrears engines (§2-4 of
  the same architecture doc) are Sprint 20's own explicit split in the
  roadmap, not this sprint's — the same "one architecture section, two
  sprints" pattern as Compliance (Sprints 15-17).
- **`Tenant.contact_details` is a free-form JSON map**, not fixed
  columns — same non-fabrication stance as `StockConditionSurvey.
  condition_ratings` (Sprint 18): this build has no authoritative
  source for exactly which contact fields every org needs.
- **`Lease.lease_status` is an enforced workflow** (DRAFT → ACTIVE →
  EXPIRED/TERMINATED/RENEWED, all terminal) — same transition-dict
  pattern as Repair/Defect/Hazard status. `Lease.occupancy_status`
  (OCCUPIED/NOTICE_GIVEN/VACANT) is deliberately *not* a workflow — a
  tenant can go OCCUPIED → NOTICE_GIVEN → OCCUPIED again if notice is
  withdrawn, so it's freely settable rather than transition-checked.
  `contractual_rent_pence`/`service_charge_amount_pence` follow this
  codebase's universal pence-not-float money convention.
- **Tenant/Lease endpoints are not restricted by organisation type** —
  the adaptive workspace layout only controls nav visibility and
  "tenant" → "occupier" terminology for commercial-type orgs; it's a
  UI decision, not an API capability gate, the same way every other
  domain's nav slicing has always worked in this codebase.
- **RBAC first real use**: `commercial.read`/`commercial.write` have
  existed since Sprint 1 (COMMERCIAL_PROPERTY_MANAGER, LEASE_MANAGER,
  RENT_MANAGER) but had nothing to gate until now — same "give an old
  permission its first real use" pattern as Sprints 14/15/17/18.
- **Property 360's stale `not_yet_available` entry closed**:
  `"tenancy_and_lease (Sprint 19)"` is now composed for real (a
  property's leases, sorted newest-first). While fixing it, found —
  but deliberately left out of this sprint's scope — that two other
  entries in the same list (`compliance_and_safety`,
  `stock_condition_and_planned_investment`) are similarly stale: both
  have had real canonical tables since Sprints 15-18 but still aren't
  composed into Property 360 itself. Reworded those two entries to be
  honest about *why* they're still listed (tables exist; composition
  doesn't) rather than leaving the original, now-misleading wording,
  and flagged the actual composition work as a separate follow-up task
  rather than scope-creeping three sprints' worth of View changes into
  this one.
- `apps/web`: `/tenancies` (tenant register + add form) and `/leases`
  (property+tenant pickers, lease register with enforced status-
  transition buttons and freely-settable occupancy buttons) replace
  their `ComingSoon` stubs. The Property detail page gained a Leases
  section composed from the same Property 360 data the backend fix
  above unlocked.
- 25 new backend tests (244 total passing): tenant/lease CRUD, lease
  status transitions (happy path and an illegal skip), occupancy's
  freely-settable behaviour, list filtering, permission checks
  (REPAIRS_MANAGER denied, LEASE_MANAGER allowed), cross-org 404, the
  new `LEASE` reference pattern, and Property 360's lease composition.
- Verified end-to-end live: created a tenant and a lease through the
  real `/tenancies`/`/leases` UI, advanced the lease from DRAFT to
  ACTIVE, and confirmed it appeared correctly composed — with the
  right status badge — on the property's own detail page, including
  the corrected `not_yet_available` wording.

**Sprint 20 — Rent / Payments / Arrears:**

- **Completes architecture/05-commercial-domain.md §1's schema**:
  `RentObligation` (what's owed), `PaymentTransaction` (what was
  received), `PaymentAllocation` (the only join between the two) — kept
  as three separate tables, never a combined ledger row, because spec
  §52's exact/possible/partial/overpayment/unallocated matching is
  inherently many-to-many (one payment can cover several obligations;
  one obligation can be paid in instalments).
- **Payment boundary (spec §54) enforced by construction, not just
  policy**: the endpoint is literally named `POST /payments`, not
  `/payment-transactions` — matching architecture's own wording, since
  the point it's making (*record* a payment, never *initiate* one) is
  the whole reason for the name. There is no charge/transfer endpoint
  anywhere in this codebase.
- **`reconciliation.py`: `match_payment` implements spec §52's four
  ordered rules exactly** — exact reference match → exact amount+lease+
  due-date-window match → partial-amount candidate → no match →
  `UNALLOCATED`, with `NEEDS_REVIEW` at any step where a rule finds
  *more than one* equally-plausible candidate obligation rather than
  guessing. Only a rule finding exactly one candidate auto-allocates —
  `MATCHED` for the confident rules, `POSSIBLE_MATCH` for the partial-
  amount rule specifically, since a partial payment is inherently less
  certain than an exact one. "Never silently allocate ambiguous money"
  (spec §52) enforced by the algorithm's own shape, not a comment.
- **Every payment gets exactly one `PaymentAllocation` row from the
  first automatic pass**, even when nothing matched (`rent_obligation_id`
  NULL, status `UNALLOCATED`/`NEEDS_REVIEW`) — the row is itself the
  "this payment was considered" record, surfacing directly in the
  `/rent-and-payments` work queue for a RENT_MANAGER to resolve.
  Resolution updates that row in place with `source_type = MANUAL`
  (architecture §2's own words), audited the same way every write in
  this codebase is. Splitting one payment across several obligations is
  a separate, deliberate manual act (`POST /payments/{id}/allocations`)
  — the automatic reconciler never does this itself.
- **`arrears.py` implements §3's `arrears_for_lease`/`collection_rate`
  pseudocode closely** — both pure, computed at read time, only
  `MATCHED` allocations count as "collected" (not `POSSIBLE_MATCH`/
  `NEEDS_REVIEW`/`UNALLOCATED`, which would blur spec §52's "never
  allocate ambiguous money" into the reporting layer too). Ageing
  buckets (`CURRENT`/`1-30`/`31-60`/`61-90`/`90+`) are computed per
  obligation from its own outstanding balance, not its full amount, so
  a partially-paid obligation only contributes its unpaid remainder.
- **One deliberate, documented deviation from the purely-computed-at-
  read-time norm this codebase otherwise follows everywhere**:
  reconciliation runs *once*, when a payment is recorded, not
  re-evaluated on every subsequent read — a config change (e.g.
  widening the due-date window) affects payments recorded after the
  change, not retroactively. This matches how a real reconciliation
  workflow behaves (a bank reconciliation, once done, isn't silently
  redone every time someone views it) and is documented explicitly at
  the top of `test_rent_payments_arrears.py` and `reconciliation.py`.
- **`commercial.payments` gets its first real use** — RENT_MANAGER-only,
  narrower than `commercial.write` (COMMERCIAL_PROPERTY_MANAGER/
  LEASE_MANAGER/RENT_MANAGER), gating the money-recording endpoints
  specifically. Same pattern as `operations.compliance` (Sprint 15).
- `apps/web`: `/rent-and-payments` (obligation register per lease,
  payment recording with live reconciliation-result feedback, and the
  needs-attention work queue with inline resolve controls) and
  `/arrears` (per-lease ageing snapshot, portfolio collection rate)
  replace their `ComingSoon` stubs.
- 16 new backend tests (260 total passing): one isolated test per
  reconciliation rule (including both the confident-match and
  ambiguous/`NEEDS_REVIEW` branch of rules 1 and 2), the due-date-
  window config-change test, manual resolution and its "already
  matched" guard, manual split allocation and its overallocation
  guard, a full arrears snapshot (overdue + current + overpaid +
  unallocated in one lease), collection rate, and permission checks
  (LEASE_MANAGER denied on payments, RENT_MANAGER allowed).
- Verified end-to-end live: through the real `/rent-and-payments` UI,
  added a rent obligation, recorded an exactly-matching payment and
  watched the live reconciliation result ("MATCHED") and the
  obligation flip to "settled" without a page reload; recorded a
  second, deliberately unmatchable payment and confirmed it appeared
  in the needs-attention queue as `UNALLOCATED`. Confirmed the
  `/arrears` page composed the same lease's snapshot correctly —
  £0 outstanding, the unallocated payment counted separately, and a
  correct 100% collection rate for a period with nothing due in it.

**Sprint 21 — Cross-Domain Attention Engine:**

- **This codebase's first genuine scheduled background job.** Every
  prior "computed at read time" engine (Data Health, Handover
  Readiness, Planned Investment, Sprint 17's compliance_status) noted
  this is where a real scheduler would eventually land — this sprint
  is that landing. `app/worker/main.py` (idle since Sprint 1, a
  heartbeat loop with "0 jobs registered") now runs the Attention
  Engine's nightly scan for every organisation, once per UTC day at a
  configurable hour, with no new scheduling dependency (no APScheduler/
  Celery) — a plain hour-check-plus-last-run-date guard on the existing
  loop, since there's exactly one job to run.
- **Four rules, matching architecture's own four named examples**:
  `WARRANTY_EXPIRING_WITH_OPEN_DEFECT` (the worked example in the
  architecture doc, implemented as given — a join of Sprint 11's
  Warranty and Defect on the same component/property),
  `REPEAT_FAILURE` (wraps Sprint 14's repeat_repairs_for_property /
  repeat_failures_for_component — reads that engine's own already-
  computed signal, never recomputes a repair count),
  `COMPLIANCE_BREACH` (wraps Sprint 17's compliance_status, surfacing
  entities where a currently-applicable requirement's computed status
  is a genuine breach — OVERDUE/OVERDUE_ACTION/MISSING_EVIDENCE — not
  the merely-advisory DUE_SOON/NEEDS_REVIEW), `LEASE_ARREARS` (wraps
  Sprint 20's arrears_for_lease, flagging active leases over a
  configurable outstanding threshold). Every rule is a join + threshold
  over an already-built engine — none restates another domain's logic,
  per architecture's own explicit instruction.
- **Deliberate deviation from the SQL sketch's `organisation_id NULL`
  global-catalog allowance**: `AttentionRule` is always org-scoped,
  lazily seeded per (org, code) — the same RepairRuleConfig/
  PlannedInvestmentWeight/ComplianceStatusConfig shape, not the
  ComponentType/ComplianceDomain shared-catalog shape. Reasoning: the
  four rule *types* are fixed Python functions, not data the rule
  engine interprets — there's no rule-authoring DSL in this build, so
  there's no real catalog to browse or fork from. Building one just to
  honor a literal NULL column would mean a `rule_definition` field
  nobody's code interprets as logic.
- **`explanation` always answers spec §55's four questions** (what,
  why, supporting_record_ids, recommended_investigation), stored as
  data so every signal type renders uniformly rather than needing
  bespoke copy per rule.
- **Upsert semantics, tested explicitly**: a rule firing again for the
  same (rule, entity) while a signal is still OPEN/ACKNOWLEDGED
  refreshes that row in place (no duplicate). A signal a human
  DISMISSED is never silently recreated — the dismissal is respected.
  A RESOLVED signal firing again gets a genuinely new row, since a
  fresh occurrence after resolution isn't a duplicate of the resolved
  one. Caught and fixed during this sprint's own test-writing: the
  first implementation only checked for OPEN/ACKNOWLEDGED signals
  before creating a new row, which silently defeated the DISMISSED
  suppression it was supposed to provide — a real bug, caught by the
  test written to prove the opposite behaviour.
- **Second real bug caught during testing**: `GET /attention/rules`
  lazily seeds the four default rules but was missing the `db.commit()`
  every other lazy-seeding list endpoint in this codebase already
  calls (compliance domains, repair rule configs, ...) — the seeded
  rows were visible within that one request's own transaction but
  silently rolled back on connection close, so a subsequent request
  using a rule's `id` from that response got a 404. Fixed by adding
  the same `db.commit()` pattern; regression-tested.
- **RBAC reuse, no new permission invented**: signal viewing/triage
  (acknowledge/resolve/dismiss) is gated by `reports.read` — every
  custom role in this build's RBAC table already holds it, so this is
  closer to "any active member" than a real restriction today, which
  is an intentional, low-risk choice (triaging an alert isn't a
  sensitive write on core domain data). Rule configuration
  (`is_active`, `rule_definition`) and manually forcing a rescan are
  gated by `reports.board` — the same executive-level gate Board
  Assurance (Sprint 17) uses, since reshaping how the whole
  organisation's insights feed is computed is an org-wide decision.
- `apps/web`: the Home dashboard gained a "Needs attention" section —
  every OPEN signal with its full explanation, a severity badge, a
  link to the relevant entity where one exists, and inline Acknowledge/
  Resolve/Dismiss actions that update live without a page reload. No
  separate rules-management page yet (the API fully supports it,
  verified by tests) — not building a settings UI nobody asked for yet
  is the same proportionate-scope call every prior sprint has made.
- 14 new backend tests (274 total passing): one per rule's own
  cross-domain composition (including a true-negative case for the
  warranty rule), the upsert-refresh/dismiss-respects/resolve-recreates
  semantics, rule deactivation, the multi-org worker entrypoint's
  tenant isolation, and permission checks.
- Verified end-to-end live: recorded three repairs against one
  property through curl, confirmed the four rules seeded correctly,
  triggered a scan and got back the expected `REPEAT_FAILURE` signal
  with its full four-part explanation. Through the real Home page UI,
  confirmed the same signal rendered in the "Needs attention" section
  with a working link to the flagged property, then clicked Resolve
  and watched it disappear live.

**Sprint 22 — Ask DataLume:**

- **The full pipeline architecture §1 specifies**: DATA → ... →
  DETERMINISTIC ANALYTICS → CONTROLLED AI TOOLS → LLM INTERPRETATION →
  USER. `app/intelligence/ask/tools.py` exposes seven typed tools —
  `get_compliance_status`, `get_repeat_repairs`, `get_repeat_failures`,
  `get_arrears`, `get_planned_investment`, `get_property_360`,
  `get_defects` — every one a thin wrapper around an already-built
  deterministic engine (Sprints 11/13/14/17/18/20). None computes
  anything new; the three architecture names explicitly
  (`get_compliance_status`, `get_repeat_repairs`, `get_arrears`) are
  implemented exactly as named.
- **Tool selection is deterministic application code
  (`pipeline.py.select_tools`), never delegated to the LLM's own
  judgement** — a keyword router matches the question's text against
  each tool's registered keywords, scoped to the entity types that
  tool actually supports. This is a deliberate strengthening of spec
  §57's "never invent" guarantee beyond what native function-calling
  would give: with native tool-use, the *model* decides which query to
  run; here, which tools execute is fully deterministic, code-reviewed,
  and unit-tested, and the LLM (when configured) only ever sees
  results that already came back from real queries — never gets to
  choose what to query.
- **`ToolResultOut`/`AskResponseOut` implement architecture §2's own
  contract field-for-field** (`dataset`, `fields`, `filters`,
  `time_period`, `records`, `calculation` / `answer_text`,
  `tool_results`, `grounded`, `suggested_follow_ups`) — the same shape
  spec §58 Explainability and the mobile app's `<GroundedClaim>`
  pattern both expect, so a future mobile client could consume this
  exact API unchanged.
- **`grounded=False` is enforced in the API layer, not hoped for in a
  prompt**: when no tool matches the question for the given entity,
  `pipeline.py` returns a fixed "I don't have data to answer that"
  message and an empty `tool_results` list *before* any LLM is ever
  called — spec §56/§91's "say so explicitly rather than guessing" is
  structural, not a system-prompt request that an LLM could ignore.
- **`app/integrations/llm_provider.py` follows Sprint 2's
  `BillingProvider` precedent exactly**: a `Protocol` boundary,
  `NullLLMProvider` active whenever `ANTHROPIC_API_KEY` is unset (the
  case in this environment), and a real `AnthropicLLMProvider` using
  the official `anthropic` Python package (added as a real dependency
  this sprint) for when a key is configured. Unlike Stripe, an
  unconfigured LLM doesn't take the whole feature down: the LLM is
  architecture's own narrowest, final step — turning already-grounded
  `ToolResultOut` rows into prose — so `NullLLMProvider` still runs the
  full deterministic pipeline and falls back to a templated summary
  built from each tool's own `calculation` field, never a fake
  interpretation. Every test in this sprint runs against
  `NullLLMProvider`, since no key is configured here, proving the
  entire grounding pipeline works independently of whether an LLM is
  available — exactly the property spec §57 is trying to guarantee.
- **Deliberate substitution of the Python `anthropic` package for the
  architecture doc's literal `@anthropic-ai/sdk` (the JS/TS package)**:
  every other domain and integration in this codebase lives in the
  FastAPI backend (`apps/api`) — Stripe, sessions, storage, every
  sprint's business logic — and `intelligence/ask/`'s own tools are
  explicitly specified as "Python functions with typed signatures."
  Introducing a second server-side runtime in the Next.js app just to
  match one package name, with no functional benefit, would break that
  established pattern for no reason; the Python SDK fills the
  identical role.
- `apps/web`: `/ask` replaces its `ComingSoon` stub with a real
  chat-style page — pick what kind of record to ask about (building/
  property/component/lease), pick the specific record, ask a free-text
  question, and see the grounded answer with a `Grounded`/`No data`
  badge, an expandable "show the data behind this answer" panel
  (dataset/fields/filters/calculation/record count per tool call — the
  Explainability rendering spec §58 asks for), and clickable suggested
  follow-ups.
- 10 new backend tests (284 total passing): one per tool's own
  grounded composition, the ungrounded fallback, a tool/entity-type
  mismatch correctly staying ungrounded, a planned-investment question
  against a component with no expected life (still grounded, factor
  correctly inapplicable), and a cross-org isolation check confirming
  a tool resolves to "not found" rather than leaking another
  organisation's data when asked about a foreign entity_id.
- Verified end-to-end live: through the real `/ask` UI, asked a
  building "Is this building's gas safety compliance up to date?" and
  watched the `get_compliance_status` tool's grounded result render
  with the full explainability panel (dataset, fields, filters,
  calculation, record count) and suggested follow-ups; asked an
  off-topic question and confirmed the fixed "I don't have data"
  message rendered instead of any guess, with no explainability panel
  shown since no tool ran.

**Sprint 23 — Reporting:**

- **architecture §4: "a report is a rendering target, not a separate
  data path."** `app/reports/content.py` builds all five named report
  types (Development Summary, Handover Readiness, Compliance Executive
  Summary, Board Assurance, Commercial Portfolio) entirely by
  composing already-built service-layer functions
  (`get_portfolio_summary`, `compute_handover_readiness`,
  `get_board_assurance_report`, `collection_rate`/`arrears_for_lease`)
  into one generic `ReportContent` shape (headline fields + tables).
  Nothing in this sprint computes a new number.
- **Compliance Executive Summary and Board Assurance intentionally
  read the same data path** (`get_board_assurance_report`, portfolio-
  wide) — spec item 57 only formally defines one assurance
  methodology, and §4 explicitly allows one data path to back more
  than one rendering target. They differ only in altitude: Board
  Assurance renders the full per-domain breakdown table; Compliance
  Executive Summary renders only the headline totals, for a one-page
  exec readout.
- **PDF/XLSX/CSV via ReportLab/openpyxl/csv** — ReportLab over
  WeasyPrint (architecture names both) since it's pure-Python with no
  system Cairo/Pango dependency, the same "needs no external service to
  implement and verify for real" preference that picked
  LocalFilesystemStorage over a cloud SDK in Sprint 4. CSV is
  inherently flat: for the two multi-table report types, it renders
  the report's primary table only, documented on the section itself
  rather than silently dropped.
- **Report generation runs on this codebase's now-real worker loop**
  (`app/worker/main.py`, built for real in Sprint 21) — architecture §4
  explicitly requires background generation "never... in the
  request/response cycle," and unlike Sprint 3's `ImportJob` (which had
  no real queue to run on yet and stayed synchronous, an honest,
  documented scope gap), the infrastructure to do this for real now
  exists. `ReportJob` follows `ImportJob`'s own shape almost exactly.
  Report jobs are on-demand, not nightly, so the worker's tick was
  shortened from 30s to 5s and now polls for PENDING report jobs every
  tick, alongside the existing once-a-day attention scan check — still
  a plain DB poll, no new scheduling dependency.
- **Board-level report types reuse the existing `reports.board`
  permission**, the same gate the `/assurance-report` JSON endpoint
  (Sprint 17) already enforces — Compliance Executive Summary and Board
  Assurance both read that same data, so letting any `reports.read`
  holder export it as a file would have been a permission regression
  through a side door. Checked at both request-time and download-time.
- **A real bug caught only by running the worker as its own process**,
  not by pytest: `ReportJob.requested_by` is the worker's first foreign
  key to a table (`users`) outside its own job code's transitive
  imports. SQLAlchemy only resolves a string-based ForeignKey against
  classes actually imported in the current process; `app/worker/main.py`
  never imported anything that pulled in `app.auth.models`, so the
  first report job processed by a real, standalone worker process
  crashed with `NoReferencedTableError` — invisible to the pytest suite
  because `app/tests/conftest.py` already imports `app.main` (and
  therefore every model) to build its FastAPI test client. Fixed by
  having `app/worker/main.py` import `app.main` at startup, registering
  every domain's models the same way the API process does. Found during
  this sprint's own two-process live verification (API + worker as
  separate processes against the same SQLite file), not by a unit test.
- `apps/web`: `/reports` replaces its `ComingSoon` stub with a real
  page — report/format pickers (with Building/Property scope fields
  appearing only for the two board-level types), a "Generate report"
  button, and a live-updating table of recent report jobs that polls
  every 3s while anything is still PENDING/RUNNING, with a Download
  button once a job reaches READY. Nav entry already existed
  (`app/organisations/adaptive.py`), unchanged.
- 9 new backend tests (293 total passing): PDF/XLSX/CSV generation and
  download for three of the five report types, the `reports.board`
  permission boundary (MANAGER 403, EXECUTIVE 200) on both board-level
  types, download-before-ready returns 400, cross-organisation 404 on
  both the status and download endpoints, and list ordering.
- Verified end-to-end live: ran the API and worker as two genuinely
  separate processes against one shared SQLite file (not the pytest
  in-process fixture), confirmed via curl that a PDF and an XLSX report
  download as valid files (`%PDF` magic bytes; a real Excel 2007+ zip
  container), then in the real browser UI generated a Handover
  Readiness CSV report and watched its status go PENDING → READY with
  no manual refresh — the page's own 3s poll picked up the worker's 5s
  tick automatically — then generated Compliance Executive Summary
  (with its Building/Property scope fields correctly appearing only for
  that report type) and clicked Download, confirming a real 200 OK
  network request. All four report types tried this way generated
  successfully; Commercial Portfolio is covered by its own dedicated
  backend test instead, since it needs a commercial-landlord
  organisation with lease/rent data this session's browser account
  wasn't set up as.

**Sprint 24 — Security / Performance / Accessibility / Pilot Hardening:**

This is the roadmap's last sprint, scoped as a genuine hardening pass
rather than a new feature — architecture/09's own scope ("Full
threat-model pass, security test suite, a11y audit, load testing,
Northstar demo data complete, backup drill") is broader than one sprint
can build for real in this sandboxed environment (no Postgres, no real
Redis, no cloud target, no load-generation infra), so this sprint
picked the pieces genuinely buildable and verifiable here, fixed every
real bug they surfaced, and documents the rest as an honest scope-out
rather than a checkbox — the same discipline every Stripe/OTel/backup
mention has had since Sprint 2.

- **Tenant isolation fuzz test suite** (spec §75's own wording,
  `app/tests/test_security_tenant_isolation.py`): one org creates one
  instance of all 15 GET-by-id resource types this codebase exposes
  (spanning every domain — development, operations, compliance,
  commercial, documents, reports); a second, genuinely separate
  membership then attempts to read every one of them and must get a
  clean 404 (never 200, never a 500 that could leak a stack trace).
  Also verifies the reverse (the owning org still reads its own data
  through the same URLs — a suite that passed because every route
  404s unconditionally would be worthless) and a representative
  write-path IDOR check, a forged-org-header-without-membership check,
  and a read-only-role-cannot-write sweep across two roles. **Result:
  every resource type passed on the first run** — no cross-tenant leak
  found. This directly answers `STATUS.md`'s own standing "treat
  tenant isolation as unconfirmed" note from earlier sprints, at the
  *application* layer (query-scoping + membership checks); Postgres
  RLS itself is still unverified, since this environment has no
  Postgres to run it against — see the "Not yet done" note below,
  updated rather than just repeated.
- **A real audit-event gap, found by re-reading architecture/09 §1's
  own threat table against the actual code**: "Report/export
  endpoints... are themselves audit events" — Sprint 23's
  `reports/router.py` never called `record_audit_event`, unlike every
  other write path in this codebase. Fixed: both requesting and
  downloading a report now write an `AuditEvent` row (download is the
  real export moment, and a report can be downloaded more than once).
- **Structured JSON logging, for real** (architecture §3): before this
  sprint only `app/worker/main.py` used `structlog`, with no
  `structlog.configure(...)` anywhere, so it ran on unconfigured
  defaults. `app/core/logging.py` configures a real JSON renderer
  process-wide; `app/core/request_logging.py` is a new middleware
  binding `request_id`/`organisation_id`/`actor_user_id` via
  structlog's contextvars so *every* log line emitted anywhere during
  a request carries them automatically, not just one summary line —
  and every response now carries a matching `X-Request-Id` header.
  `actor_user_id` is resolved read-only from the same Redis session
  store `get_current_user` already uses, without extending the
  session TTL just because a request happened to be logged.
- **A real robustness bug, caught by this sprint's own concurrency
  smoke-check** (below): the new logging middleware's actor-id lookup
  had no error handling, so a Redis hiccup during that best-effort,
  logging-only lookup took down the *entire* request with a 500 — not
  just requests that actually needed Redis for real auth. Every single
  request failed in the check until this was found. Fixed with a
  try/except around the lookup (log a warning, continue with
  `actor_user_id=None`); regression-tested by monkeypatching in a
  Redis client that always raises and confirming the request still
  succeeds.
- **A real DoS gap, found during the threat-model pass**: the same
  table's "file type/size allow-list" mitigation didn't exist — every
  upload endpoint (`documents`, `document versions`, CSV `uploads`)
  read an unbounded request body into memory. `app/core/uploads.py`'s
  `read_upload_within_limit` (a 25MB default, `max_upload_size_bytes`
  in settings) now backs all three, returning a clean 413 over the
  limit. File *type* allow-listing is deliberately not implemented —
  `UploadFile.content_type` is client-supplied and spoofable, and a
  real check needs magic-byte sniffing; a check against only the
  untrusted header would be false confidence, not a mitigation, so
  it's left as a documented gap rather than a hollow one.
- **Northstar demo data, for both named orgs**
  (`scripts/seed_demo.py`, rewritten): seeds Northstar Housing (2
  developments — one fully built out, one mid-construction — 3
  buildings, 8 properties, components, a specification with change
  control, defects in different states, a boiler warranty expiring
  within 90 days, four repeat Plumbing repairs on one property, a gas
  safety requirement compliant on one building and missing evidence on
  two others, a damp & mould hazard, a stale stock condition survey)
  and Northstar Commercial (3 units, 3 tenants/leases, rent
  obligations, and payments landing in three different real outcomes —
  fully reconciled, partially paid and sitting in `POSSIBLE_MATCH`
  pending human review, and entirely unpaid) — then runs a real
  attention scan for each org. The old Sprint 1 version's "~12,480
  properties" placeholder is replaced with a documented, deliberate
  choice: variety across every engine this build now has (handover
  readiness, repeat repairs, compliance status, attention signals,
  arrears/collection rate), not raw row count. Drives the real FastAPI
  app in-process via `TestClient` rather than hand-reconstructing every
  service function's kwargs, so every payload is the same shape this
  codebase's own test suite already verified against the real API.
  Coarser-grained idempotent (skips an org's domain data entirely if
  it already has any developments/leases) rather than per-row deduped
  across ~15 resource types — verified by running it twice against the
  same database and confirming the second run only reused the existing
  org/login and skipped domain seeding.
- **A real accessibility bug, found and fixed**: `components/
  AuthCard.tsx`'s `FieldLabel` rendered a `<label>` as a sibling of its
  `<input>`, with no `htmlFor`/`id` pairing — confirmed via
  `element.labels` returning empty in the browser, meaning a screen
  reader gets no accessible name for any sign-in/sign-up field. Fixed
  by making `htmlFor` a required prop and adding matching `id`s on
  both pages; verified via `element.labels` returning the correct
  label text afterward. The same unassociated-label pattern was found
  in 18 more files across the authenticated app (an inlined label
  style rather than a shared component, plus one dynamically-generated
  form — `planned-investment/page.tsx`'s per-factor weight inputs,
  found by a follow-up sweep after the initial 17-file grep missed its
  slightly different label style) — closed out immediately after this
  sprint rather than left as a standing gap; see the dedicated note
  below.
- **A concurrency smoke-check, explicitly not a load test**: this
  sandbox has no realistic multi-user load generator and the
  smoketest server runs SQLite (single-writer), not the Postgres this
  app is architected for — spec §72's real performance requirement is
  unverified and stays that way until this runs against real infra.
  What this sprint *could* honestly check: whether the new Sprint
  23/24 machinery falls over under a modest concurrent burst. 50
  concurrent `GET /api/v1/properties` requests: 0 errors, p50 55ms,
  p95 70ms, max 75ms (after the Redis-outage fix above — before it,
  every single request failed).
- 15 new backend tests (308 total passing): the tenant isolation suite
  (5), the reports audit-event regression (1), request-logging
  behaviour including the Redis-outage regression (6), and the upload
  size limit (3).

**Post-Sprint-24 — closing the label-association follow-up:** all 24
roadmap sprints were complete, so this picked up the one concrete item
Sprint 24 itself flagged rather than leaving it as a queued task. Every
`<label>` across the authenticated app that was a sibling of its
`<input>`/`<select>` (not nested, not associated) got a matching
`id`/`htmlFor` pair — 18 files in the end: the 17 found by Sprint 24's
own grep, plus `planned-investment/page.tsx`, caught by a repo-wide
re-grep after the fact because its label style (`fontSize: 11,
marginBottom: 2`, one property literally different) didn't match the
pattern the first search looked for — worth noting since it's exactly
the kind of gap a single grep pattern can miss. That file's weight
inputs are also the one genuinely dynamic case (a `.map()` over factor
codes rather than a fixed form), fixed with `id={`weight-${w.factor_
code}`}` so each generated input still gets a unique, stable id. The
one non-visible-label case (`ask/page.tsx`'s free-text question input,
which only ever had a placeholder) got `aria-label="Question"` instead
of a visible label, to avoid a layout change. Verified two ways: a
repo-wide `grep -rn '<label'` with no `htmlFor` hits left afterward,
and live in the browser via `element.labels` on `/reports`,
`/planned-investment` (including three of the five dynamically-id'd
weight inputs, confirming no id collisions), and `/ask` — all resolved
to the correct label text. `npm run build`/`lint` both clean; no
backend changes, so the existing 308 backend tests are unaffected.

**Post-Sprint-24 — publishing the repo and closing the CI gap:** the
repo is now public on GitHub with a real README (the old one was a
Claude Code handoff-package doc from before the build started),
CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, CHANGELOG.md,
CODEOWNERS, and a PR template — all grounded in this codebase's actual
conventions rather than generic boilerplate. `.github/workflows/ci.yml`
closes the "no CI pipeline wired up yet" gap for real (verified before
first push: a genuinely fresh venv install ran all 308 tests clean).
`.github/workflows/codeql.yml` adds static analysis for both languages
in this repo. `.github/dependabot.yml` covers all three dependency
surfaces (pip, npm, GitHub Actions); once enabled it opened 5 PRs, 4 of
which were verified (locally, not just trusting the green badge — see
below) and merged, and one left open on purpose:
`typescript-eslint` doesn't yet support the TypeScript 7.0 it was
trying to bump to (`npm run build` passes, `npm run lint` doesn't) — a
real, current upstream gap, not a bug here, reproduced locally before
deciding not to merge it. The python-dependencies PR turned out to be
a no-op for what actually installs (`pyproject.toml` has no lockfile,
so `pip install` was already resolving to those same versions) — still
verified with a fresh venv + full 308-test run before merging, same
discipline as everything else in this build, not just because CI
showed green.

**Post-Sprint-24 — a first real Playwright E2E suite
(`apps/web/e2e/`):** closes part of the gap above. Seven specs across
five files: sign-up lands on the home dashboard and reflects the real
org name (auth.spec), sign-out actually blocks re-entry to `/home`
(auth.spec), a Development->Building->Property chain created through
the real UI shows up correctly in the portfolio summary's
`properties_by_status` badge (golden-thread.spec), an unanswerable
question gets Sprint 22's fixed "I don't have data" message with no
explainability panel, never a guess (ask-datalume.spec), adding a
requirement under a pre-seeded compliance domain (Gas Safety, not a
throwaway one — Sprint 15's 21 global domains are real seed data)
shows up in its list (compliance.spec), an unpaid rent obligation
shows as fully outstanding on the arrears page (commercial-
arrears.spec, Sprints 19-20), and a requested report genuinely goes
PENDING -> READY with no page reload and downloads a real file
(reports.spec, Sprint 23's own background-job guarantee, watched
through the worker's real 5s poll tick, not a mock).

`apps/api/scripts/run_smoketest_server.py` (the SQLite+fake-Redis
pattern used for every live verification all through this build) and
its new sibling `run_smoketest_worker.py` are both real, checked-in
scripts now — `playwright.config.ts`'s `webServer` array starts the
API, then the worker, then `next dev`, in that order (Playwright starts
array entries sequentially, each waiting on its own readiness signal,
so the worker never starts before the API's `--fresh` table
(re)creation has finished). Without the worker, `reports.spec.ts`
would watch a report job sit PENDING forever — this is genuinely
worker-driven, not simulated. `npm run test:e2e` (or the `e2e` CI job)
needs nothing beyond the repo itself, no Docker/Postgres/Redis.
Explicitly not spec §76-78's full 50-step acceptance suite — see the
"Not yet done" note for what's still unwritten.

Two real bugs found while building this, not just the tests
themselves:
- The first CI run of the original 4-spec suite failed immediately
  (exit code 127) — `playwright.config.ts` hardcoded
  `apps/api/.venv/bin/python`, which only exists in local dev; CI's
  `pip install -e ".[dev]"` has no venv at all and installs onto
  `actions/setup-python`'s own Python. Fixed by detecting the venv at
  config-load time and falling back to `python3`. Verified on GitHub's
  own runner afterward, not just locally.
- Writing `commercial-arrears.spec.ts` required reading `/arrears`'s
  actual source, which turned up a lease `<select>` with no label at
  all — not caught by Sprint 24's original 17-file sweep (a
  single-line grep pattern) or its own follow-up (18 files), since
  there was nothing for either to match on. A properly AST-shaped
  check (matching the full multi-line `<input>`/`<select>` tag, not a
  single grep line) found 7 more of the same kind across the app —
  dense, per-row inline-editing controls with no visible label at all.
  All fixed with `aria-label`.

Verified repeatedly before pushing: normal dev mode and `CI=true`
(fresh servers, `github` reporter) both green, run twice each to check
for timing flakiness in the worker-dependent reports test — no
flakiness observed across 4 total local runs.

**Post-Sprint-24 — the real `StripeBillingProvider`:** closes the
Sprint 2 deferral. `app/integrations/billing_provider.py` now has a
full implementation behind the same `BillingProvider` Protocol
`NullBillingProvider` always used, so nothing above the adapter
boundary changed shape. `create_checkout_session` uses inline
`price_data` (currency/amount/recurring/product) rather than requiring
Price/Product objects pre-created in a Stripe dashboard, so there's no
manual dashboard setup step before this works against a real test-mode
key. `create_billing_portal_session` opens Stripe's own hosted portal.

The webhook handler (`POST /api/v1/subscriptions/webhook`, unauthenticated
by design — signature verification is the entire auth mechanism, per
architecture/09 §1's threat table) is the sole writer of billing state
derived from Stripe, matching architecture/07 §2. Because Stripe
doesn't guarantee webhook delivery order, `organisation_id` is written
into the Checkout Session's `subscription_data.metadata` at creation
time so it lands on the resulting Stripe Subscription object itself —
every `customer.subscription.*` event can resolve the DataLume org
directly from the event payload, whether or not `checkout.session.completed`
has been processed yet. Handles `checkout.session.completed`,
`customer.subscription.created/updated/deleted`, and
`invoice.payment_failed/succeeded`.

Fully tested offline, no live Stripe account needed: `stripe.WebhookSignature.
generate_signature_header` generates a validly-signed test payload with
zero network calls, so `test_billing.py` exercises real signature
verification (`stripe.Webhook.construct_event`) and the entire
event-dispatch state machine, not a mock of it — ~15 new tests, all
passing (320 backend tests total). Two real bugs found and fixed while
building this:
- Stripe's current API moved `current_period_end` off the top-level
  Subscription object onto `subscription["items"]["data"][0]` (multiple
  prices per subscription support) — confirmed by grepping the
  installed SDK's own type stubs, not assumed from memory.
- The SDK's `StripeObject` deliberately doesn't support `.get()` like a
  plain dict (`AttributeError: 'get' is a dict method, but a
  StripeObject is not a dict`) — the webhook dispatcher now converts
  via `.to_dict()` before handing the event object to a handler
  function.

`apps/web/organisation/billing/page.tsx` already called `/checkout`;
this pass added the missing "Manage billing" button wired to
`/portal` (the API client already had `startBillingPortal`, unused
until now) — without it there was no way for a subscriber to reach
Stripe's portal to update a card, cancel, or see invoices. Both
buttons degrade the same way against `NullBillingProvider`: a 503
becomes an inline "isn't wired up yet, contact us" message, not a
broken redirect. `npm run build`/`lint` both clean.

**What's still genuinely unverified**: `create_checkout_session` and
`create_billing_portal_session` have never been called against a real
Stripe account — this sandbox has no live `STRIPE_SECRET_KEY`. The
webhook state machine is real and tested; the two calls that actually
talk to Stripe's API are not. Needs a Stripe test-mode secret key +
webhook signing secret to close that gap for real.

**Post-Sprint-24 — the membership-invite flow:** closes the gap this
same document used to flag under "Not yet done" — signup could only
ever create a single OWNER, with no way for them to add a colleague.
`app/auth/models.py` already had `Membership.status` (including an
unused `INVITED` value) and `invited_by` anticipating this since
Sprint 1, but `Membership.user_id` is required, so it can't represent
someone who doesn't have a DataLume account yet — the common case for
a real invite. A new `Invitation` table (migration `0022_invitations`)
holds the pending offer instead: organisation, email, role, an
unguessable `secrets.token_urlsafe(32)` token, and a 7-day expiry.

There's no email-sending integration anywhere in this codebase (same
gap Stripe had until this session) — rather than fake one, the invite
endpoint hands the accept link straight back in the response, and
`/organisation/users` shows it as a copy-to-share link with an
explicit "no email configured" note, the same honest degradation
Stripe's checkout/portal buttons use. The public accept endpoints
(`GET/POST /api/v1/invitations/{token}...`) have no auth dependency at
all — the token itself is the entire authorization, the same role the
Stripe webhook signature plays for that endpoint. Deliberately no
Postgres RLS on the `invitations` table either, and the migration says
why: the accept flow needs to look a row up by token before the
visitor has any org membership to scope by, so there's no
`app.current_org_id` yet at that point — the authenticated
list/create/revoke endpoints filter by organisation in application
code instead, same as every route already does at the app layer.

Accept handles three cases: a brand-new email creates the account
(name + password) and auto-logs in; an already-registered email
requires the visitor to be signed in as that exact address (never
silently logs anyone into an existing account); and being signed in as
a *different* account is refused with a clear "sign out first"
message rather than silently doing the wrong thing. `org.manage_members`
is gated the same way `billing.manage` already was — never spelled out
per role in `rbac.py`, so it only resolves true through the OWNER/ADMIN
wildcard.

`/organisation/users` (previously a bare `ComingSoon` stub) is now a
real page: an invite form, a pending-invitations table with copy-link
and revoke actions, and a members table. A new public
`/accept-invite` page (`apps/web/src/app/(marketing)/`) renders all
three accept states.

10 new backend tests (330 total passing), covering: invite/list/revoke,
duplicate-pending and already-a-member conflicts, an unknown role code,
permission denial for a non-owner, the full accept flow for a new
account, the existing-account sign-in-first flow (and successfully
accepting a second organisation's invite once signed in as that user),
an expired invitation, and cross-organisation isolation. `npm run
build`/`lint` both clean. Verified live in-browser end to end: signed
up an OWNER, invited a colleague as Manager, opened the link as a
second, signed-out session, created their account, confirmed they
landed in the org — and confirmed the Manager (correctly) can't see
the Users management screen themselves, only Owners/Admins can.

## Not yet done

Sprint 24 closed out the roadmap's stated 24 sprints. What's left is
what Sprint 24 itself found couldn't be done for real in this sandbox,
plus what earlier sprints already flagged — not a "next sprint," a
punch list for whoever takes this toward a real pilot:

- **RLS is still unverified against real Postgres** — this sprint's
  tenant isolation suite confirms the *application* layer (query
  scoping + membership checks) holds for all 15 resource types
  checked, a stronger result than existed before, but the Postgres
  Row Level Security policies in `alembic/versions/0001_foundation.py`
  onward have still never actually run against a live database.
  Treat RLS itself as the remaining unconfirmed half of architecture
  01 §1's two-layer tenant isolation.
- **Real load testing against Postgres-backed infra** — spec §72's
  actual performance requirement (portfolios in the tens of
  thousands) is unverified; this sprint's concurrency smoke-check
  (above) is a much smaller, explicitly-labelled substitute.
- **A real backup drill** — architecture §5's Postgres snapshot/WAL
  archiving and object-storage versioning are both infra-managed
  (Azure-side), not application code to write; there's no real
  Postgres/cloud storage in this sandbox to actually drill a restore
  against.
- **Full OTel/Sentry wiring to a real collector** — architecture §3
  names both; this sprint built the structured-logging half for real
  (see above) since it's independently valuable and fully verifiable
  here, but didn't add span-based tracing, since there's no real
  collector in this sandbox to send spans to and a half-wired tracer
  would be worse than a documented gap.
- **The Playwright E2E acceptance suite covers a real first slice, not
  the full 50 steps.** See the dedicated note above for what exists
  now (auth, the Development->Building->Property golden thread, Ask
  DataLume's ungrounded-question guarantee, a compliance requirement
  against a seeded domain, commercial arrears, and worker-driven
  report generation) and what's still genuinely unwritten — handover
  authorisation, defects/warranties, repeat-repair detection, the
  attention engine (there's no scan-trigger button in the UI at all,
  only the nightly worker job — not currently E2E-testable without
  either adding one or a much longer-running test), and most of spec
  §76-78's deeper Housing Operations and Commercial scenarios.

Specifically flagged as gaps to close early, not deferred to "later":

- **The Reference Engine's first-ever pattern row per org+entity_type
  still has a narrow bootstrap race.** Row-locking only protects reads
  of an *existing* `ReferencePattern` row; two simultaneous first-ever
  creates of the same entity_type for the same org could both attempt
  the initial insert. A unique constraint turns that into a clean
  `IntegrityError` rather than a silent duplicate, but it isn't caught/
  retried — a real (if unlikely) gap, documented in
  `identifiers/service.py`.
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
  live database. Sprint 24 added the security tests architecture/09 §2
  asks for (`app/tests/test_security_tenant_isolation.py`) and they
  pass — but against the SQLite test fixture, which has no RLS at all;
  they confirm the *application*-layer tenant scoping, not the second,
  Postgres-only layer. Treat RLS itself as still unconfirmed until
  that same suite (or an equivalent) runs against real Postgres.
- **Stripe checkout/portal are unverified against a live account.**
  `StripeBillingProvider` is now implemented (see the Post-Sprint-24
  entry above) and its webhook logic is fully tested offline, but
  `create_checkout_session`/`create_billing_portal_session` have never
  been exercised against a real Stripe account — this sandbox has no
  `STRIPE_SECRET_KEY`. Needs a real test-mode key to confirm those two
  calls for real. See `app/integrations/billing_provider.py`.
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
  `app.core.tenancy` / `app.auth.router` / `app.core.request_logging`
  (Sprint 24's new logging middleware also holds its own bound
  reference) with an in-process fake before starting uvicorn —
  `app.tests.conftest.py`'s fixture is the reference implementation of
  all three. Import `app.main` (not just `app.core.db`) before calling
  `Base.metadata.create_all(engine)`, or the model modules never
  register their tables and `create_all` silently does nothing — this
  bit the first version of the throwaway script used to verify Sprint 2
  end-to-end. The same "import app.main first" rule applies to
  `app/worker/main.py` too as of Sprint 23 — see that module's own
  docstring for the NoReferencedTableError this caused when it didn't.
