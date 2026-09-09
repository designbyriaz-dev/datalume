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

## Not yet done

Sprints 16–24 (compliance operations, stock condition, tenancies, and
the rest) — not started. Full order and scope in
`architecture/10-roadmap-and-acceptance.md`.

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
