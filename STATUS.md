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
  `pipeline.py`'s module docstring): **CSV only**, no XLSX/XLS yet
  (closed Post-Sprint-24 — see the dedicated entry below).
  VALIDATE/UNDERSTAND/IMPORT all run **synchronously** in the upload
  request for now, not as a background job — the DB shape already
  matches the background-job design, so moving IMPORT later (done
  Post-Sprint-24, see below — a plain DB-poll worker job, not the RQ
  queue this note originally guessed at) was a call-site change, not a
  schema change; not done yet in Sprint 3 because there was no working
  background worker at all to move it onto (same reasoning as Sprint
  2's Stripe deferral — build what's genuinely testable now).
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

**Update — the full Stripe round-trip verified for real (2026-09-11):**
the user supplied a real Stripe test-mode `STRIPE_SECRET_KEY`
(`apps/api/.env`, gitignored, never committed), then installed
Homebrew and the Stripe CLI so the loop could close completely rather
than stopping at "checkout session creation works":

1. `stripe listen --forward-to localhost:8000/api/v1/subscriptions/webhook`
   run against the real account, giving a real `whsec_...` signing
   secret (also added to `.env`).
2. A real checkout session created via the API, opened in an actual
   browser, and paid with Stripe's standard test card
   (`4242 4242 4242 4242`) — a genuine test-mode payment, not a
   simulation.
3. Stripe's own webhook delivery (not a synthetic signed payload)
   reached the local server for every event in the real sequence —
   `charge.succeeded`, `invoice.paid`, `invoice.finalized`,
   `payment_method.attached`, `customer.created`,
   `checkout.session.completed`, `customer.updated`,
   `customer.subscription.created`, `payment_intent.*`,
   `invoice.created`, `invoice.payment_succeeded` — every single one
   answered `200`, including the handled types (signature verification
   passed for real) and the unhandled ones (the "log and no-op, don't
   crash" fallback path, also exercised for real for the first time).
4. `GET /api/v1/subscriptions` afterward showed the organisation's
   subscription had flipped to `ACTIVE`, plan `STARTER`, correct
   `£99`-derived entitlements, and a `current_period_end` exactly one
   month out — Stripe's own webhook delivery had written real state
   into this database, closing the loop this document has called
   "genuinely unverified" since Sprint 2.

`create_billing_portal_session` verified the same way in a second full
cycle (fresh org, fresh checkout, fresh `stripe listen` session): the
returned `billing.stripe.com` URL opened to a real, fully-populated
portal — correct plan (`DataLume Starter, £99.00 per month`), the real
test card (`Visa •••• 4242`), correct next billing date, correct
customer name/email, and a real paid `£99.00` invoice in the history.
`billing_portal.configuration.created` and
`billing_portal.session.created` webhooks both delivered and answered
`200` too. Every part of `StripeBillingProvider` this codebase can
exercise without a production deployment has now actually been
exercised end to end, not just unit-tested against synthetic payloads
— nothing about Stripe billing remains "unverified" in this document.

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

**Post-Sprint-24 — TOTP-based MFA:** `User.mfa_enabled`/`mfa_secret`
existed since Sprint 1 but nothing set or checked them — this closes
that gap for real using `pyotp`, no external provider needed (unlike
Stripe/email, TOTP is a self-contained standard, not something this
sandbox lacks credentials for).

`POST /api/v1/auth/mfa/enroll` generates a secret and returns a
manual-entry key (`otpauth://` URI too, though nothing renders it as a
QR code yet — any authenticator app accepts typed-in keys the same
way). Enrolling doesn't turn MFA on by itself: `mfa_enabled` only
flips to `True` once `/mfa/verify` confirms the app is actually
producing matching codes, the same "the thing existing isn't the same
as it being active" distinction Stripe's checkout session vs. active
subscription already draws. `/mfa/disable` requires the current
password, not just an active session, before turning it back off.

Login changes shape for an MFA-enabled account: password-correct no
longer issues a session directly. `POST /auth/login` returns a
short-lived, single-use `mfa_token` (Redis-backed, 5-minute TTL,
hashed the same way a real session token is before it touches Redis)
instead, and `POST /auth/mfa/challenge` exchanges that token plus a
6-digit code for the actual session — deleted on first use, so a
captured token can't be replayed even inside its own TTL window. A
non-MFA account's login response shape changed too (`{mfa_required:
false, user_id}` instead of a bare `user_id`) — every caller (this
codebase's own tests included) was updated for it.

A real bug found while verifying this live rather than just against
the SQLite test suite: `scripts/run_smoketest_server.py` and
`run_smoketest_worker.py` each keep their own standalone `FakeRedis`
class (they're not pytest, so they can't use `conftest.py`'s), and
neither had a `.delete()` method — the pytest fixture's FakeRedis
did, so the test suite never exercised the missing method and every
automated check passed while the smoketest server 500'd on the very
first real challenge attempt. Fixed in both scripts; worth noting as
a reminder that this build's two parallel "fake infrastructure"
implementations can drift, and only one of them gets exercised by
`pytest`.

9 new backend tests (339 total passing). `/settings` (previously a
`ComingSoon` stub) now has a real two-factor section; `/sign-in`
handles the two-step challenge. `npm run build`/`lint` both clean.
Verified live end to end in-browser: enrolled, verified with a
real computed TOTP code, signed out, and confirmed a plain password
was no longer enough to sign back in until the second code was
entered correctly.

**Post-Sprint-24 — MFA backup/recovery codes:** closes the gap the
entry above flagged immediately after shipping MFA — until now, losing
the authenticator device meant permanent lockout, a real usability
consequence with no recovery path at all.

`/mfa/verify` (turning MFA on) and a new `/mfa/backup-codes/regenerate`
(password-confirmed, for topping up or resetting after a lost device)
both replace the user's whole code set with ten fresh ones —
`XXXXX-XXXXX`, drawn from an alphabet with `0/O/1/I` excluded so a
handwritten copy stays unambiguous — and hand them back in plaintext
exactly once; only the bcrypt hash is stored (`MfaBackupCode`,
migration `0023`, no RLS for the same reason `sessions`/`users`/`roles`
don't get it: this is user-level data, not organisation-scoped).
`/mfa/challenge` tries the submitted code as TOTP first, then as a
backup code if that fails, so login needs no separate "I don't have my
app" path — the same field just accepts either shape. A used code is
marked (not deleted, so misuse is still auditable) and can never work
again; regenerating invalidates every code from the previous batch,
used or not.

7 new backend tests (346 total). `/settings` shows the backup codes
once right after enabling (with a "copy all" and an explicit "I've
saved these" acknowledgement before continuing) and a running "N
backup codes remaining" count with a regenerate action afterward;
`/sign-in`'s challenge step now says a backup code works too and
accepts the longer format. Verified live end to end: enabled MFA, saw
the 10 codes, signed out, signed back in with one of them instead of a
TOTP code, and confirmed the remaining count dropped to 9.

**Post-Sprint-24 — Reference Engine bootstrap race, actually closed:**
this document used to flag `identifiers/service.py`'s narrow gap
honestly rather than pretend it away — two simultaneous *first-ever*
`generate_reference` calls for the same org+entity_type could both miss
the row-locked SELECT and both attempt the bootstrap insert, with only
the DB's unique constraint stopping a duplicate. Now caught: the
insert runs inside a SAVEPOINT (`db.begin_nested()`), and an
`IntegrityError` there triggers a re-read of the row the "winner" just
committed (same row lock the steady-state path already takes) instead
of surfacing the error to whatever request happened to lose the race.
Genuine concurrent-thread testing against SQLite would exercise a
different failure mode than Postgres here (SQLite serializes writers
at the whole-database level and raises `OperationalError`, not the
row-lock + unique-constraint interplay this fix targets), so the race
is deterministically simulated instead — one new test forces the
first `_select_pattern` call to miss a row a "concurrent" transaction
already committed, confirming recovery rather than a crash or
duplicate. 1 new backend test (347 total).

**Post-Sprint-24 — CSV import for Developments and Buildings:**
closes the other half of the same honestly-flagged gap — only
`PROPERTIES` (Sprint 5) and `COMPONENTS` (Sprint 8) had a field
dictionary and a registered importer; a real housing association's
onboarding data is Developments and Buildings as much as Properties,
and until now every one of those had to be hand-created through the
UI before a single Property CSV could even reference them. (`Floor`
already existed as a full domain model since early on — this
document's own gap note calling out "floors" was stale; Floor CSV
import specifically is still unadded, see below.)

New field dictionaries for both dataset types (`ingestion/
field_dictionary.py`) and `import_development_row`/`import_building_row`
(`development/importers.py`), registered into the same `IMPORTERS` seam
PROPERTIES/COMPONENTS already use — no frontend change needed at all,
since `/data-and-uploads`'s dataset-type dropdown was already driven
entirely by the field-dictionary API response, not a hardcoded list.
Buildings can optionally link to an already-imported Development via
an internal `development_reference` (`DEV-000001`) column — the only
identifier a CSV can realistically carry, since the real UUID doesn't
exist until that row was created — resolved by lookup at import time;
a blank or unmatched reference leaves the building unlinked rather
than failing the row, same permissiveness PROPERTIES' importer already
has toward its own (still entirely unwired) hierarchy links.

Found and fixed a real, pre-existing, unrelated gap while wiring this:
`number_of_planned_properties` has been a real column on `Development`
since Sprint 6, but neither `CreateDevelopmentRequest` nor
`DevelopmentOut` ever exposed it — the manual-entry API couldn't set
it and couldn't show it back, even though the demo data's own "84
homes" language depends on exactly this field. Fixed in the schema,
both presenter functions, and the manual-create router, not just the
new importer's path.

`create_development`/`create_building` also didn't accept
`source_dataset_id`/`import_job_id`/`original_reference` at all before
this — `create_property`/`create_component` already did, so those two
were the only service functions in this domain that couldn't honestly
stamp file-upload provenance. Fixed to match.

6 new backend tests (350 total, plus the schema-completeness fix
above). Verified live: a real multipart CSV upload against a running
smoketest server (not just pytest's TestClient) for both dataset
types, including the fuzzy column-mapping correctly auto-matching
every header with no manual correction needed, and the
development_reference linking resolving to the right Development.

**Post-Sprint-24 — XLSX upload:** closes a real onboarding barrier
this document used to flag honestly rather than paper over — most UK
housing-association teams work in Excel day to day, and CSV-only meant
every real dataset needed a manual export step before it could reach
DataLume at all. `openpyxl` was already a dependency (used for report
export since Sprint 23) but nothing used it for *reading* a file.

`parse_xlsx` (`ingestion/pipeline.py`) returns the exact same
`(headers, ParsedRow list)` shape `parse_csv` always has, so every
downstream stage — VALIDATE, field-dictionary matching, cleaning,
every importer — is genuinely format-agnostic; a new `parse_upload`
dispatches on the filename's `.xlsx` extension (a convenience, not a
security control — `UploadFile.content_type` is client-supplied and
spoofable, same reasoning `core/uploads.py` already documents for why
this pipeline doesn't do content-type allow-listing). `CsvParseError`
is renamed `FileParseError` since it's no longer CSV-specific.

The real complexity wasn't the parsing call itself but the type
boundary: openpyxl hands back real Python `int`/`float`/`date`/`bool`
values per cell, while every downstream consumer (field validation,
`_parse_int`/`_parse_iso_date` in the domain importers) expects plain
strings the way a CSV cell always is. A `_xlsx_cell_to_str` normaliser
handles this once at the parse boundary rather than leaking openpyxl's
types into the rest of the pipeline — including collapsing an
integer-valued float (openpyxl's usual shape for a whole-number cell)
to `"6"`, not `"6.0"`, so `storeys`/`number_of_planned_properties`
parse identically regardless of which format the row came from.
Legacy binary `.xls` stays out of scope — a different, largely-
unmaintained library for a format Office hasn't defaulted to since
2007.

6 new backend tests (356 total): a real property import from an XLSX
workbook end to end, typed-cell conversion, a corrupt file returning a
clean 400 rather than a 500, an empty workbook, and blank-row
skipping. `/data-and-uploads` accepts `.xlsx` in its file picker and
no longer tells users XLSX isn't supported. Verified live against a
running smoketest server (not just pytest's TestClient) with a real
openpyxl-built workbook: property import including a comma-containing
address value that would need CSV-quoting but needs nothing special in
a spreadsheet cell, and the same typed-storeys conversion confirmed
over the real HTTP path.

**Post-Sprint-24 — a manual "Run scan now" for the Attention Engine:**
closes a real UX gap this document flagged under the E2E section — the
Cross-Domain Attention Engine only ever ran via a nightly worker job,
so a pilot org had no way to see it work without waiting for actual
nightfall. The backend endpoint already existed
(`POST /api/v1/attention/scan`, `reports.board`-gated) and even had a
frontend client method (`triggerAttentionScan`) — both sat completely
unused, with no button anywhere calling either. This closes that
purely on the frontend: a "Run scan now" button next to Home's "Needs
attention" section, shown only to OWNER/ADMIN/EXECUTIVE (checked
client-side against `/auth/me`'s membership role, matching the same
roles the backend's wildcard/`reports.board` grant already allows —
the button doesn't invite a click that can only ever 403), showing a
plain-English result ("3 new, 1 updated" / "No new signals — everything
checked out") and refreshing the signal list afterward.

While in this code, fixed a real, narrow concurrency gap the manual
trigger makes far more reachable than it was: previously only one
nightly cron ever called `upsert_signal`, so its check-then-write
(SELECT for a live signal, then INSERT if none exists) was safe in
practice even without a lock. A user able to click "Run scan now" any
time — including while the nightly job happens to be running, or via
a double-click — could race that same check-then-write and create two
OPEN rows for the same (rule, entity). Fixed the same way the
Reference Engine's analogous bootstrap race was closed earlier this
sprint: a partial unique index (live OPEN/ACKNOWLEDGED rows only —
unlimited RESOLVED/DISMISSED history for the same (org, rule, entity)
is legitimate) now declared directly on `AttentionSignal.__table_args__`
(migration `0024`) actually enforced in both dialects. `upsert_signal`
recovers from the resulting `IntegrityError` by re-reading the
winner's row rather than surfacing the error, deterministically tested
the same way as the Reference Engine fix (SQLite can't reproduce true
Postgres-style concurrency, so the race is simulated: the first lookup
is forced to miss a row a "concurrent" scan already committed).

Fixing that surfaced a second, identical gap right next to it:
`AttentionRule`'s own `uq_attention_rule_org_code` constraint — which
`get_or_create_rule` has the exact same unprotected-bootstrap-insert
race around as `upsert_signal` did — turned out to only ever exist in
`0020_attention_engine.py`'s migration, never declared on the model
itself, so SQLite's `Base.metadata.create_all` (what every test
actually runs against) never enforced it either. Fixed the same way,
immediately rather than left as a noted-but-unfixed gap: the
constraint now lives on `AttentionRule.__table_args__` too (no new
migration needed — Postgres already has it via `0020`), and
`get_or_create_rule` recovers from the same `IntegrityError` class,
with its own deterministic race test.

Also fixed, unrelated but found the same way the Stripe key exposed
the conftest.py gap below: `apps/api/.env` now holding a real Stripe
key meant `pytest` silently picked it up too (pydantic-settings reads
`.env` relative to cwd, and `get_settings()` is `@lru_cache`'d and
first triggered by module-level `settings = get_settings()` bindings
at import time, before any fixture runs) — flipping
`test_owner_checkout_fails_with_not_configured_not_forbidden` from
`NullBillingProvider` behaviour to the real provider and failing it.
`conftest.py` now forces `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`
to empty strings before `app.main` is ever imported, so tests stay
hermetic regardless of whatever a developer's local `.env` holds for
manual verification.

2 new backend tests (358 total) — one race-recovery test for each of
`upsert_signal` and `get_or_create_rule`; the rest of the existing
attention suite passes untouched by the refactor. `npm run build`/
`lint` both clean. Verified live end to end:
signed up, saw "Run scan now" on Home with "Nothing needs attention
right now", clicked it, and got back "No new signals — everything
checked out" with no error — the same result a passing backend test
suite already proves the scan logic itself produces correctly for a
portfolio with actual repeat-failure/compliance/arrears/warranty
patterns in it.

**Post-Sprint-24 — QR code rendering for MFA enrolment:** closes the
one remaining gap MFA's own entry above flagged — enrolment only ever
showed the manual-entry setup key, which every authenticator app
accepts but is meaningfully slower than a scan. `qrcode` (MIT,
actively maintained) added to `apps/web`'s dependencies — the first
new runtime dependency this frontend has needed since scaffolding —
and rendered client-side via its browser-safe entry point
(`QRCode.toDataURL`), directly from the same `otpauth_url` the manual
key was already built from, so both encode identically; no backend
change needed. The manual key stays visible underneath the code rather
than being replaced by it — a real device without camera access, or a
desktop-only authenticator, still works exactly as before. A failed
QR render (`toDataURL` rejecting) degrades to manual-entry-only rather
than blocking enrolment.

`npm install qrcode @types/qrcode`; `npm run build`/`lint` both clean.
Verified live end to end: enrolled, saw a real rendered QR code
alongside the setup key, and — rather than just checking the image
appeared — computed the TOTP code from the same secret text shown
underneath and completed verification with it, confirming the QR
encodes a genuinely working `otpauth://` URI, not just that an image
tag renders.

**Post-Sprint-24 — a real Playwright spec for the Attention Engine's
manual scan:** closes the E2E gap the manual-trigger entry above left
open. Three repairs of the same category against one property — the
exact repeat-failure pattern `test_attention.py`'s own worker test
already uses to get a real `signals_created == 1` — reported through
the actual `/repairs` form, then "Run scan now" clicked on Home:
asserts the "1 new, 0 updated." result text, the signal's real
explanation copy ("... repairs reported against this property..."),
and "Needs attention (1)". 8 E2E specs total now. Verified both ways
this suite always is: normal dev mode and `CI=true`, run twice each,
no flakiness.

**Post-Sprint-24 — CSV import for Floors, closing the trio:**
Developments and Buildings closed earlier; Floor is the third and
last hierarchy level a real portfolio needs bulk import for. Unlike
Building's optional `development_reference`, Floor's `building_id` is
a required FK — a floor genuinely cannot exist without a building, so
an unmatched `building_reference` can't just leave the row unlinked
the way an unmatched development link does.

That forced a real, useful fix rather than a workaround: `import_dataset`
had no per-row failure handling at all — a single row's importer
raising anything would abort every remaining valid row in the job with
a 500, a latent gap in every importer this pipeline has ever had, not
new to this one. A new `ImporterRowError` (deliberately distinct from
a bare exception, so a genuine bug still surfaces as a real 500 rather
than being silently swallowed) lets `import_floor_row` mark just its
own row `INVALID` with a clear message and move on. `ImportResultOut`
gained `rows_failed`; `/data-and-uploads` shows it when nonzero.
`create_floor` also didn't accept `source_dataset_id`/`import_job_id`/
`original_reference` before this — the same gap `create_development`/
`create_building` had until the CSV-import entry above fixed those two;
now all three match `create_property`/`create_component`.

3 new backend tests (361 total): a real two-floor import linked to an
existing building, one unmatched reference failing only that row while
the other still imports, and a missing-required-field rejection at the
MAP+REVIEW stage. Verified live against a running smoketest server:
uploaded a real 3-row CSV (two valid, one deliberately bad), got
`rows_failed: 1` back, confirmed the two good floors exist with the
right `building_id`, and confirmed the bad row's exact error message
(`"No building found with reference 'BLD-999999'"`) rather than a
generic failure.

**Post-Sprint-24 — three more Data Health checks from spec §42's real
15-item list:** Sprint 5 only had Property to check against; every
domain model spec §42 names now exists, so this closes a real dent in
the gap rather than the whole thing. All three follow `rules.py`'s own
established shape exactly — a new function, appended to `RULES`, no
router/schema/frontend change needed (the Home KPI card, Property 360,
and `/api/v1/data-health` all already read the same registry).

`ORPHAN_COMPONENT`: a `Component` with *all five* of its
development/building/property/space/parent-component links unset isn't
loosely scoped, it's disconnected from the property hierarchy entirely
— spec §24's whole point. `DUPLICATE_COMPONENT`: the same
Counter-over-a-normalised-key shape `check_duplicate_properties`
already uses, keyed on type + exact location + manufacturer/model —
two components at the same place, of the same type and make/model, is
a near-certain accidental double-entry. `MISSING_HANDOVER_INFORMATION`:
a property already marked `HANDED_OVER` with no matching
`HandoverRecord` row (the permanent evidence a real handover happened,
written in the same transaction as that status flip) — evidence
missing, whatever the reason.

3 new backend tests (364 total), following the existing suite's own
pattern exactly (real HTTP calls through the actual endpoints; a raw
session only for the one field — `HandoverRecord`, no dedicated
"mark handed over" endpoint exists — with no API surface). Confirmed
`scripts/seed_demo.py`'s own component/property data doesn't trip any
of the three new checks — every seeded component has a real
`property_id`, and nothing is marked `HANDED_OVER` — so the demo orgs'
health scores don't shift.

**Post-Sprint-24 — the ingestion pipeline's IMPORT step moved to the
worker, closing the background-job-queue gap flagged since Sprint 3:**
spec §72's "tens of thousands of properties" performance requirement
was real — a synchronous `import_dataset` call blocked the request
that triggered it for as long as the whole file took to commit. The
gap's own earlier language ("behind a real RQ+Redis queue") was never
accurate: this codebase has no `rq` dependency and never did. What
actually exists — and what this uses — is the plain DB-poll worker
already built for report generation (Sprint 23): `POST
/datasets/{id}/import` now just flips the job to `IMPORTING` and
returns `202`; `worker/jobs/ingestion.py`'s `process_pending_import_jobs`
(this worker's third registered job) picks it up on the next 5s tick
and runs the exact same `import_dataset` as before. `ImportJob` gained
four nullable result columns (`rows_processed`, `entities_created`,
`rows_failed`, `importer_registered` — migration `0025`) so the result
survives past the request that started the job; `GET /datasets/{id}`
already returned job status and now returns these too, so no new
polling endpoint was needed. UPLOAD/VALIDATE/UNDERSTAND/MAP/REVIEW all
stay synchronous — MAP+REVIEW's proposed mapping has to return to the
browser immediately for a human to review, so only the step after
human review moves to the background.

Row-level failures (one bad row) were already handled inside
`import_dataset` itself (`ImporterRowError` -> that row marked
`INVALID`, the job carries on); what's new is a genuine exception now
marks the whole *job* `FAILED` with `error_summary` set, since there's
no HTTP request left to return a 500 to once this runs off-cycle —
mirrors `app.reports.service.process_report_job`'s exact convention.

12 existing test call sites across `test_ingestion.py`, `test_components.py`,
and `test_development.py` updated to trigger the (now 202) import and
drive it through `process_pending_import_jobs` directly against a raw
session — the same pattern `test_reports.py` already established for
report generation — rather than wait on a real ticking worker process.
Frontend (`data-and-uploads/page.tsx`) gained the same poll-while-
in-flight pattern `reports/page.tsx` already uses (2s interval while
`latest_job_status === "IMPORTING"`), plus a new Playwright spec
(`data-and-uploads.spec.ts`) watching a real upload go
MAPPED -> IMPORTING -> COMPLETED with no page reload and confirming the
imported property is real, not mocked. Verified live end-to-end outside
the test suite too: ran the smoketest API + worker as two real
processes, uploaded a CSV through curl, watched the job sit `IMPORTING`
until the worker's own log line (`ingestion_import.tick`,
`jobs_processed: 1`) showed it picked the job up, then confirmed both
properties existed with correct provenance.

364 backend tests, all still passing — 12 existing call sites adapted
to the new async contract, no new test functions needed.

**Post-Sprint-24 — a real Playwright spec for handover authorisation:**
closes one of the two named gaps in the Playwright suite's own "still
genuinely unwritten" list. `HANDOVER_READINESS_THRESHOLD_PCT` is 100%
and a freshly created property has none of the stock-condition-survey/
documentation history the readiness score reads, so this deliberately
doesn't contrive an "already ready" property — it drives the real
Development -> Building -> Property setup through the UI (the same
pattern `golden-thread.spec.ts` established), flips a property to
`READY_FOR_HANDOVER`, confirms authorising with no override reason is
genuinely rejected server-side (not just gated in the UI), then
authorises with one and confirms the property really becomes
`HANDED_OVER` and the handover history shows the record with its
override reason. 10 Playwright specs total, all passing.

**Post-Sprint-24 — five more Data Health checks: serial numbers,
installation dates, conflicting references, duplicate documents:**
closes as much of spec §42's remaining list as is real, not noisy, to
implement right now — see `rules.py`'s own module docstring for the
three items deliberately left out and why (missing component types is
vacuous, missing evidence needs tracking this codebase doesn't have,
missing warranties/specifications/building-relationships would be
blanket rules with no per-type "should have one" flag to scope them,
flagging components and properties that plausibly shouldn't have one).

`MISSING_SERIAL_NUMBER` (LOW) and `MISSING_INSTALLATION_DATE` (MEDIUM)
follow the exact established shape — the former identical to
`check_missing_uprn`, since Component's serial number lives in
`ExternalReference` for the same reason UPRN does (its own model
docstring). `INVALID_INSTALLATION_DATE` (HIGH) catches a genuinely
impossible value (installation dated in the future) on components that
already have a date, the same "applies only to the present case, not
double-counted with the missing check" pattern
`check_stale_stock_condition_survey` established.

`CONFLICTING_EXTERNAL_REFERENCE` (HIGH) surfaced a real, previously
undetected data-integrity gap: `ExternalReference` has no uniqueness
constraint on `(entity_type, entity_id, reference_type)` — two
different UPRNs recorded for the same property is a state this schema
has always allowed, silently masked in reads by
`get_external_references_bulk`'s `dict.setdefault` quietly keeping
only one of them. `DUPLICATE_DOCUMENT` (MEDIUM) catches identical
content uploaded as two separate documents (different `lineage_id`)
rather than a new revision of one, scoped to `ACTIVE` so genuine
version history sharing a checksum isn't flagged.

Writing `test_data_health_flags_missing_installation_date` surfaced a
real pre-existing bug in `scripts/seed_demo.py`: it posted
`"install_date"` instead of the schema's actual `installation_date`
field when seeding Riverside Gardens' boiler components, so that value
was silently dropped by every seeded boiler ever created — fixed
alongside this sprint's own checks, the same way the Floor-import
pipeline reliability fix surfaced from a stricter downstream
constraint earlier this session. Confirmed the rest of
`scripts/seed_demo.py` doesn't touch documents or external references
at all, so the two new document/reference checks don't trip on demo
data; `MISSING_SERIAL_NUMBER`/`MISSING_INSTALLATION_DATE` do fire
against the demo org's components, honestly, since the demo data really
doesn't set those fields — LOW/MEDIUM severity by design, not treated
as a score-tanking problem.

5 new backend tests (369 total), following the same real-HTTP-call
pattern as every other Data Health test — `POST /external-references`
twice with different values for the same reference to reproduce a
genuine conflict, two document uploads with identical bytes to
reproduce a genuine duplicate, no raw DB construction needed for any
of the five.

**Post-Sprint-24 — a real Playwright spec for defects and warranties:**
closes the second of the two gaps the Playwright suite's own note
named as "still genuinely unwritten" (handover authorisation was the
first — see the dedicated entry above). Defects and warranties share a
building detail page (spec §34-35, architecture 03 §8) — this exercises
a real server-validated status transition (`DEFECT_TRANSITIONS` gates
which next-states the UI even offers, backed by
`InvalidDefectTransitionError` on the API side) rather than just the
creation form, then adds a warranty and voids it, confirming the
badge/day-count the API computes (`is_expired`/`days_until_expiry`)
actually reflects the real expiry date entered. 11 Playwright specs
total, all passing.

**Post-Sprint-24 — a real Playwright spec for change control:** spec
§76 steps 25-27 ("Record proposed change", "Preserve previous
specification", "Approve/reject change") — architecture 03 §7's
append-only revision model, untouched by any existing E2E spec despite
being a fully built, real feature (`ComponentDetailClient.tsx`).
`implement_change_control` (service.py) creates a new specification
row for the approved change and marks the old one `SUPERSEDED` rather
than editing it in place; this spec drives the real
propose -> approve -> implement lifecycle through the UI and confirms
the new revision (`rev B`, `ACTIVE`) replaces the old one in the
current-only view a user actually sees. Preservation of the superseded
row itself is already covered at the data level by
`test_specifications.py`/`test_change_control.py` — this closes the UI
side of the same guarantee, not a duplicate of it. 12 Playwright specs
total, all passing.

**Post-Sprint-24 — closed a real UI gap blocking Planned Investment
Intelligence (spec §76 step 47), not just added a test:**
`planned_investment.py`'s weighted, fully-explainable scoring engine
(architecture 03 §6) was completely built and already wired into
`ComponentDetailClient.tsx` — but `components/page.tsx`'s "Add a
component" form never exposed `installation_date`/`expected_life_years`,
even though the API always accepted both. AGE_RATIO (the largest single
factor, weight 0.35) was therefore permanently `applicable=False` for
every component any user could actually create through the UI — the
backend half of this feature was done, the frontend half wasn't,
exactly the "definition of done" gap CLAUDE.md's own build instructions
warn against. Added both fields to the form (a plain date input and a
number input, following every other form's own shape) rather than
writing a test that could only ever exercise the permanent no-data
path. New Playwright spec creates a component well past its expected
life and confirms the priority widget shows the real computed AGE_RATIO
detail text (actual years/percentage, not a canned string) plus the
other three always-applicable factors' real zero-state detail
(REPAIR_FREQUENCY/FAILURE_PATTERN/COMPLIANCE_LINKED) — CONDITION_SIGNAL
stays the one factor still gated on data only the compliance domain's
Inspection flow can supply, left as-is rather than forced. 13 Playwright
specs total, all passing.

**Post-Sprint-24 — closed the "link evidence to exact component" gap
(spec §76 steps 22-23), same "backend built, frontend incomplete"
pattern as Planned Investment Intelligence:** `Document.
related_entity_type`/`related_entity_id` (documents/models.py) and
`upload_document`'s matching form fields have always existed and
`GET /documents` has always supported filtering by them — but
`api.uploadDocument`/`listDocuments` never passed them through, and no
page ever exposed a way to scope an upload to a specific entity, so a
component's construction evidence was unreachable from the UI even
though the data model was ready for it. Added an "Evidence" section to
`ComponentDetailClient.tsx` (upload form + list + download, mirroring
`data-and-uploads/page.tsx`'s own document section) and extended both
API client methods with an optional related-entity parameter —
backward compatible, the existing untargeted-upload call site on
data-and-uploads still works unchanged. New Playwright spec uploads
evidence against a component and confirms it's genuinely linked, not
just uploaded: the same document shows up in the org-wide documents
list (data-and-uploads) *and* survives a full page reload scoped to
just this component, proving both views read the same
`related_entity_type`/`related_entity_id`, not a coincidence of local
component state. 14 Playwright specs total, all passing.

**Post-Sprint-24 — a real Playwright spec for Property 360's new-build
history (spec §76 step 43):** unlike the last two entries, this wasn't
a "backend built, frontend incomplete" fix — both the development/
building lineage breadcrumb and the post-handover readiness record were
already fully built and rendering real data on
`PropertyDetailClient.tsx`, just never given dedicated E2E coverage.
`golden-thread.spec.ts` already proves the portfolio summary counts a
fresh Development -> Building -> Property chain, and
`handover-authorisation.spec.ts` already proves a development's own
handover UI genuinely flips a property to `HANDED_OVER` — neither
checks what Property 360 itself shows afterwards. This closes that:
confirms the property's own page renders its lineage as real linked
entities (not a raw ID), and that after handover the readiness score
and override reason the development recorded persist into the
property's own "Handover" field — the same read the property keeps
carrying long after the development itself may be archived, exactly
the "new-build history stays with the property" guarantee spec §76
step 40 ("Preserve development history") names. 15 Playwright specs
total, all passing.

**Post-Sprint-24 — a genuinely missing Ask DataLume tool, not a UI gap
this time: "Ask questions about development" (spec §76 step 48):**
unlike the Planned Investment/construction-evidence fixes, this wasn't
backend-complete-frontend-incomplete — no tool in
`app/intelligence/ask/tools.py` ever supported
`entity_type="development"` (only building/property/component/lease),
and `development` wasn't even an option in the `/ask` page's own
dropdown, so every question about a development fell through to the
fixed "I don't have data" message, honestly but permanently. Added
`get_development_summary`, a thin wrapper around the exact same
deterministic computations the Development detail page and the
Handover Readiness report already use
(`compute_handover_readiness`, `properties_in_development`) — no new
calculation invented, same "every tool is an already-built engine"
rule this module's own docstring states elsewhere. Wired `development`
into the `/ask` page's entity-type dropdown and its record-loading
switch. New backend test (`test_development_summary_question`, 370
total) and a new Playwright spec confirm a real grounded answer with
genuine building/property counts and a handover readiness score — not
the templated no-data message, and not a hardcoded 100%. 16 Playwright
specs total, all passing.

**Post-Sprint-24 — closed Planned Investment Intelligence's last gap:
CONDITION_SIGNAL, via a real Compliance section on the component page,
not a UI-field fix this time:** `list_compliance_statuses_for_entity`
and the `Inspection` table have always supported
`entity_type="component"` (the Ask DataLume `get_compliance_status`
tool's own `applicable_entity_types` names it), but
`ComponentDetailClient.tsx` had no compliance/applicability/inspection
UI at all — only the Building page did. Extracted the Building page's
`InspectionsPanel` (previously a private, non-exported function) into
`src/components/InspectionsPanel.tsx` so both pages share one
implementation instead of two copies drifting apart, and added the
same "Add a compliance requirement" + applicability list the Building
page already has, scoped to the component. Recording an inspection now
also refreshes the Planned Investment widget (`onInspectionChanged`),
not just the compliance list — the priority score would otherwise go
stale the moment CONDITION_SIGNAL became applicable. With this, every
one of the five Planned Investment factors is genuinely UI-drivable —
AGE_RATIO and CONDITION_SIGNAL were the two "backend built, no way to
feed it" gaps this session found and closed; REPAIR_FREQUENCY/
FAILURE_PATTERN/COMPLIANCE_LINKED were already always-applicable and
needed no fix.

New Playwright spec: records a real inspection against a component and
confirms the priority widget's CONDITION_SIGNAL factor flips from
"not applicable — excluded" (the true baseline for an uninspected
component — the UI only ever renders `f.detail` when `f.applicable` is
true, so the earlier `planned-investment.spec.ts` never actually
exercised this factor's positive path) to the real inspection result
and date. 17 Playwright specs total, all passing.

**Post-Sprint-24 — Building Control and BSR references (spec §76 steps
7-8), a genuine scoring bug, not just a missing form field:**
`Building.building_control_reference`/`bsr_reference` have always been
real `ExternalReference` rows `create_building` accepts, and
`compute_handover_readiness`'s own `check_building_control_reference`
(weight 0.10) has always read them back — but no page ever exposed a
way to enter either one. That meant this check could never pass for
any building any real user ever created through the product: Handover
Readiness was permanently capped below 100% by a UI gap, not by
genuinely missing data, for every development with at least one
building. Added both fields to the "Add a building" form
(`buildings/page.tsx`, wired through `api.ts`'s `createBuilding`) and
display on `BuildingDetailClient.tsx`; also surfaced
`Development.planning_reference` on `DevelopmentDetailClient.tsx` —
already captured at creation (`developments/page.tsx`) since the CSV
importers use it, but never actually shown anywhere before.

New Playwright spec proves the fix both ways in one test, not just
that the field exists: a development whose only building has no
reference still shows the real "buildings missing a Building Control
reference" line in its readiness Missing list; a second development
whose building supplies both references at creation shows neither the
missing line nor a fake pass — the check output changes because the
underlying data genuinely changed. 18 Playwright specs total, all
passing.

Development-level `building_control_reference`/`bsr_reference` (as
opposed to the building-level pair this fixes, which is what actually
feeds Handover Readiness) remain uncaptured by the UI — left as a
smaller, honestly-documented residual gap rather than folded into this
fix, since nothing currently reads them at the development level the
way the readiness check reads the building-level pair.

**Post-Sprint-24 — spec §76 step 45, "Link repair to component":** the
repairs page's own copy has always promised this ("optionally linked
to the component that failed"), `api.createRepair`/`RepairOut` have
always carried `component_id`, and `REPAIR_FREQUENCY`
(`planned_investment.py`) has always read `Repair.component_id` — but
the "Report a repair" form never had a field for it, so no repair any
real user created could ever be linked to a component; the factor
could never show anything but "0 repair(s)".

Wiring this surfaced a second, one-level-deeper instance of the same
gap: the "Add a component" form had no `property_id` field either
(despite `api.createComponent` always accepting one), so a component
could never be placed anywhere a repair's own property-scoped dropdown
could find it — the fix was inert without also closing that one.
Fixed both: a "Component (optional)" selector on the repairs form,
scoped to whichever property is currently selected (not every
component in the org), and a "Property (optional)" selector on the
component form. The repairs register now also shows the linked
component as a real link when one exists.

New Playwright spec drives the full chain for real: creates a property,
creates a component placed at it, reports a repair against both, then
confirms both that the register row shows the resolved component link
*and* that the component's own Planned Investment widget shows a real
"1 repair(s) in the last 18 months" — not the permanent zero the UI
gap had made unavoidable. 19 Playwright specs total, all passing.

A component still can't be placed at a specific building/space, or
made a child of another component, through any UI form (only
`property_id` was added here) — `api.createComponent` already accepts
`building_id`/`parent_component_id` too, same "backend ahead of
frontend" shape, left open rather than chased indefinitely in one
sitting.

**Post-Sprint-24 — UPRN can finally be entered at property creation:**
UPRN is the flagship "never fabricate an official identifier" example
throughout the spec, and `MISSING_UPRN` has been a Data Health check
since Sprint 5 — `api.createProperty` has always accepted `uprn`
(Property 360 has always displayed it), but the "Add a property" form
never had a field for it. A manually-created property could never
satisfy `MISSING_UPRN` at all — only CSV import or a raw
`POST /external-references` call could set one, neither of which is
"enter it" the way someone working a new development by hand would
expect. Added the field, following the exact same shape as `postcode`
next to it. New Playwright spec confirms a property created without a
UPRN genuinely shows "—" (not a silent default) and one created with a
UPRN shows the real value on its own Property 360 page. 20 Playwright
specs total, all passing.

**Post-Sprint-24 — a Commercial-side audit (spec §78), the same
methodology applied to the New Build side extended to the other
acceptance test:** ran the same per-capability check (does the backend
genuinely support it, does the frontend actually expose it, is it
E2E-tested) against all 13 items in "Commercial landlord must be able
to." Most of it held up — properties/units/tenants/arrears/collection-
rate/Property-360/Ask-DataLume/reports are all genuinely built and
mostly already tested. Three real "backend built, frontend incomplete"
gaps closed:

- **Lease fields**: `break_date`, `rent_review_date`, and
  `service_charge_amount_pence` were real `CreateLeaseRequest` columns
  `api.ts`'s `createLease()` already typed and threaded through, but
  the "Add a lease" form never exposed any of the three — a landlord
  could never actually record a break clause, a rent review date, or a
  service charge. Added all three to the form and to the register row
  display.
- **Payment method**: same shape, smaller — `CreatePaymentRequest.
  method` (a plain free-text field, e.g. "BANK_TRANSFER", "CHEQUE" —
  see `PaymentTransaction`'s own docstring for why it's not an enum)
  was already accepted end-to-end but had no input on the "Record a
  payment" form.
- **Split-allocation UI**: `POST /payments/{id}/allocations`
  (`add_manual_allocation`) — "splitting one payment across several
  obligations... is a deliberate human act" per its own docstring —
  already had a working `api.ts` client method
  (`createManualAllocation`) but no UI ever called it; a landlord
  could resolve one ambiguous payment against a single obligation but
  never actually split it across two. Added a "Split across
  obligations" control to the existing "Needs attention" resolve row.

Two genuine, larger gaps found and flagged rather than folded into
this same pass: bulk/CSV import for rent obligations/payments (closed
in the very next commit, see the dedicated entry below — the audit was
right that this was a real gap, just one with a clear existing pattern
to follow rather than needing new design); and `LeaseEvent` monitoring
— `Lease.break_date`/`rent_review_date`/`lease_expiry` are stored but
nothing computes or surfaces an upcoming one (no Attention Engine rule,
no UI highlighting), unlike `LEASE_ARREARS` which is a real rule.
"Monitor lease events" genuinely needs real design work (what counts
as "upcoming," what the UI should do about it), unlike the import gap.

3 new Playwright specs (22 total, all passing): lease fields round-trip
through creation and the register display; recording a payment with a
method succeeds; and — the most substantial of the three — two
obligations sharing an invoice reference reliably reproduce a genuine
`NEEDS_REVIEW` ambiguous allocation (the same repro
`test_rule1_ambiguous_reference_needs_review` already uses at the
backend level), then the new Split control is used to peel off part of
the payment to one obligation and Resolve is used for the real
remainder — not the original £2500, proving the split actually reduced
what still needed resolving.

**Post-Sprint-24 — bulk CSV import for rent obligations and payments,
closing the Commercial audit's other real gap the same day it was
found:** `app/commercial/importers.py` registers `RENT_OBLIGATIONS`/
`PAYMENTS` into the same ingestion seam (`app/ingestion/pipeline.py`
`IMPORTERS`) every other domain's importer already uses — no new
frontend work needed at all, since `data-and-uploads/page.tsx`'s
dataset-type dropdown already reads its options from the field
dictionary registry dynamically, the same "backend registry drives
frontend automatically" pattern the whole ingestion pipeline was built
on.

Building this surfaced a real, separate bug: `RentObligation` was
missing `ProvenanceMixin` entirely — `PaymentTransaction`, created in
the exact same migration (`0019_rent_payments_arrears.py`), always had
it; `RentObligation`, three lines above it in that same file, never
did. Not a deliberate choice — CLAUDE.md's own "full data provenance
on every important record" rule doesn't carve out an exception for
"what is owed," and the importer genuinely needed
`source_dataset_id`/`import_job_id` the same way every other importer
records where a row came from. Backfilled via migration `0026`
(nullable first, backfilled existing rows as `MANUAL` — accurate,
since every rent obligation ever created so far came from the manual
form — then enforced `NOT NULL` to match every sibling table exactly)
rather than skipped or worked around.

The `PAYMENTS` importer reuses the real deterministic reconciler
(`match_payment`) per row — an imported payment gets the same genuine
matching a manually-recorded one does, never a fabricated "imported
therefore matched." `RENT_OBLIGATIONS` resolves `lease_reference` the
same way `FLOORS` resolves `building_reference` (required FK,
`ImporterRowError` marks just that row `INVALID` on a miss);
`PAYMENTS`' own `lease_reference` stays optional, mirroring
`PaymentTransaction.lease_id`'s genuine "not yet matched" case (spec
§52).

4 new backend tests (374 total) — including one that reconciles a real
imported payment against a real imported-or-manual obligation and
checks `outstanding_pence` actually reaches zero, and one confirming
an unmatched payment lands honestly `UNALLOCATED`, not a fabricated
match — plus a new Playwright spec driving the real
`/data-and-uploads` upload flow end to end (23 Playwright specs total,
all passing).

**Post-Sprint-24 — a Housing Operations audit (spec §77), the same
REAL/UI-GAP/TEST-GAP/MISSING methodology as the Commercial audit
above:** all 16 named capabilities checked against real backend,
frontend, and Playwright coverage. Found one genuine UI gap hiding
inside what looked like a test gap: `InspectionsPanel.tsx` could
*complete* a `ComplianceAction` but never *raise* one —
`api.createComplianceAction` existed in the client and the backend
service function was real, but no form anywhere ever called it. Added
a "+ Raise action" control mirroring `HazardActionsPanel`'s own
pattern (same component, used by both the Building and Component
detail pages).

Found six capabilities that were fully real end to end but had never
been given a Playwright spec — the same "already built, needs a first
UI test" pattern as every earlier entry in this list. Closed all six:
Data Health score/findings (a property with no type and no postcode
deterministically fails two checks, so the score and both findings are
guaranteed, not a guess at demo data), raising-and-completing a
compliance action (exercises the UI gap fix above), hazard tracking
through the full reported -> triaged -> investigated -> action ->
closed workflow plus a repeat damp & mould signal (`/safety` had *zero*
Playwright coverage before this despite being fully built), a
component-failure signal (`repair-linked-to-component.spec.ts` only
ever linked one repair — the signal needs three), and a board-level
report (`reports.spec.ts` only ever exercised `DEVELOPMENT_SUMMARY`;
`BOARD_ASSURANCE`/`COMPLIANCE_EXECUTIVE_SUMMARY` are real, permission-
gated report types that had never actually been requested or
downloaded).

28 Playwright specs total, all passing; full backend suite (374 tests)
and typecheck/lint unaffected by the frontend-only change.

**Post-Sprint-24 — bulk CSV import for repairs and compliance
inspections, closing the Housing Operations audit's two genuinely
missing capabilities:** `app/operations/importers.py` registers
`REPAIRS`/`COMPLIANCE_INSPECTIONS` into the same ingestion seam every
other domain's importer uses — same "no new frontend work" story as
the Commercial importers, since the dataset-type dropdown reads its
options from the field dictionary registry dynamically.

`REPAIRS` resolves `property_reference` (required FK, `ImporterRowError`
on a miss) and an optional `component_reference`, mirroring
`RENT_OBLIGATIONS`/`BUILDINGS` exactly. `COMPLIANCE_INSPECTIONS` is the
first importer to resolve a *polymorphic* entity reference — `entity_type`
(property/building/component) selects which reference field
(`property_reference`/`building_reference`/`component_reference`) the
row's `entity_reference` column is checked against, reusing the same
three entity types `RequirementApplicability`/`Inspection` already
support. Building this surfaced the same provenance gap the Commercial
audit found in `RentObligation`: `create_inspection` had no
`source_type`/`source_dataset_id`/`import_job_id` passthrough at all —
every inspection was hard-coded `SourceType.MANUAL` even though
`Inspection` already carries `ProvenanceMixin`. Extended the service
function's signature (defaults preserve existing manual-entry
behaviour) rather than bypassing provenance for this one importer.

4 new backend tests (378 total) covering both importers' happy path and
an unmatched-reference row failing only that row, plus a new Playwright
spec driving the real `/data-and-uploads` upload flow for `REPAIRS` end
to end (`COMPLIANCE_INSPECTIONS` gets backend-only coverage, same as
`PAYMENTS` did — one UI-driven spec per domain is the established
pattern, not one per dataset type). 29 Playwright specs total, all
passing.

With this, every item named in spec §77 (Housing Operations) and §78
(Commercial) is REAL except one: lease-event monitoring (see "Not yet
done" below) — genuinely missing, not a quick fix, the only acceptance-
test item left in either list that needs real design work rather than
wiring an existing capability through.

**Post-Sprint-24 — three open Dependabot PRs triaged, two merged:**
`#10` (python-dependencies group: uvicorn/sqlalchemy/alembic/psycopg/
anthropic/pyotp) and `#7` (`actions/upload-artifact` 4→7) both showed
green CI and merged cleanly. `#9` (npm-dependencies group, 9 packages)
stayed open — its "Web build & lint" check was genuinely failing, and
reproducing it locally (checking out the branch into a throwaway
worktree and running `npm ci && npm run lint` directly, since GitHub's
own raw CI logs are sign-in-gated) found the real cause: the group
bundles a `typescript` 5.9→7.0 jump, and `eslint-config-next`'s bundled
`typescript-eslint` has a hard guard that refuses to run under
TypeScript 7 at all (tracked upstream, unresolved: typescript-eslint
issue #10940). Not a config fix on this side — merging as-is would
permanently break `npm run lint` on `main`. Left open rather than
merged blind or silently worked around.

**Post-Sprint-24 — all 3 open Dependabot security alerts closed:** 1
critical (Next.js RCE in `next/og`'s Node.js `ImageResponse`
implementation, GHSA-vcvr-r3jv-pc5j — not actually exploitable here
since this app never imports `ImageResponse` from `next/og`, but a
same-minor-line patch bump, 16.3.4 → 16.3.6, removes it outright) and 2
moderate (`brace-expansion` quadratic-time/recursion DoS in dev
tooling, via `npm audit fix`). Verified with a full typecheck/lint/
build and the complete Playwright suite before pushing.

**Post-Sprint-24 — lease-event monitoring, closing spec §78's one
remaining genuinely-missing item ("Monitor lease events"):**
`LEASE_EVENT_UPCOMING` is a fifth rule in `app/attention/rules.py`'s
registry — `Lease.break_date`/`rent_review_date`/`lease_expiry` were
always real, captured fields (see the Commercial audit entry above),
but nothing computed or surfaced an approaching one. Flags active
leases with any of the three dates inside a configurable window
(default 90 days, matching the home dashboard's own existing
"warranties expiring within 90 days" convention in
`app/development/portfolio.py` rather than inventing a new number).
All three event types on one lease consolidate into a single signal,
the same "no per-sub-type column on AttentionSignal" reasoning
`COMPLIANCE_BREACH` already uses to group multiple requirement
breaches per entity.

Because the whole Attention Engine is registry-driven end to end
(`RULE_REGISTRY` → `list_rules` lazily seeds one `AttentionRule` row
per org per rule code → `run_attention_scan` iterates the registry →
Home's signal feed renders whatever `entity_type`/`explanation` comes
back generically), this needed **zero frontend code** — the existing
"Run scan now" button, rule-config endpoints, and signal feed all
picked up the fifth rule automatically, the same "backend registry
drives frontend automatically" pattern bulk CSV import has used all
along. The one new Playwright spec (30 total) is first-attempt-pass
proof of that, not a guess.

2 new backend tests (380 total) — one proving two upcoming events on
the same lease produce exactly one signal, one proving a lease with
only a far-future expiry produces none.

With this, every item named in spec §77 and §78 is genuinely REAL —
the Housing Operations and Commercial acceptance tests are both fully
closed, not "mostly."

**Post-Sprint-24 — real Postgres finally available (user-owned Homebrew
+ PostgreSQL 16 installed locally, no sudo/Docker needed), and Row
Level Security run against a live database for the first time in this
project's history.** Found and fixed two genuine bugs neither SQLite
nor this build's own dev loop had ever been able to surface, because
neither had ever run a single query against real Postgres before now:

1. `alembic_version.version_num` is hard-coded `VARCHAR(32)` by Alembic
   itself; this project's own revision IDs go up to 39 characters
   (`0017_stock_condition_planned_investment`). SQLite never enforces
   `VARCHAR` lengths, so every migration run in this sandbox's entire
   history silently tolerated it. Fixed by widening the column at
   `0015_compliance_operations_hazards` — the first revision ID in the
   chain to actually exceed 32 chars — rather than renaming any
   already-shipped revision ID.
2. `TenantScopedSession.__init__` (`app/core/tenancy.py`) ran
   `SET LOCAL app.current_org_id = :org_id` with a bound parameter —
   invalid Postgres syntax (`SET`/`SET LOCAL` are utility statements,
   parsed before bind parameters are resolved; this fails against
   SQLite too, with the same syntax error, for the same reason).
   Fixed via `set_config('app.current_org_id', :org_id, true)`, the
   documented way to set a GUC to a dynamic value with the same
   transaction-scoped reset `SET LOCAL` would give.

With both fixed, `app/tests/test_rls_postgres.py` (new) drives the
real `TenantScopedSession` class — not hand-rolled SQL — against a
live Postgres with the full 26-migration Alembic chain applied for
real, and proves, for real:
- a session scoped to Org A cannot see a row that physically exists in
  the same table but belongs to Org B;
- a session scoped to Org A cannot *write* a row claiming to belong to
  Org B — Postgres itself rejects the INSERT (`cmd = ALL` with no
  explicit `WITH CHECK` means the `USING` clause covers writes too);
- a plain session with no tenant context set at all sees **nothing**,
  not everything — RLS fails closed, the only safe default.

All 50 RLS-protected tables (`SELECT tablename FROM pg_policies`) have
`FORCE ROW LEVEL SECURITY` set, so even the owning role — which is also
the role the app connects as — is genuinely subject to every policy,
not silently exempt the way an unforced policy would let a table owner
bypass.

This also surfaced something bigger than "RLS was unverified": RLS is
correctly designed at the schema level across all 50 tables, but it
has never actually been **active** on a real application request —
see the dedicated "Not yet done" entry below for why, and what closing
it for real would take. A new `rls` CI job (`.github/workflows/ci.yml`)
runs `test_rls_postgres.py` against a real `postgres:16` service
container on every push from here on, so this verification — and this
specific gap — won't silently regress or go unnoticed again.

**Post-Sprint-24 — get_tenant_db wired into all 25 routers; RLS is now
genuinely active on every real request, not just correctly designed.**
Converted `get_tenant_db` (`app/core/tenancy.py`) from returning a
`TenantScopedSession` wrapper type to returning the same plain
`Session` back (side effect only) — the one design choice that made
this a mechanical, low-risk change: every tenant-scoped router's
`db: Session = Depends(get_db)` becomes `Depends(get_tenant_db)` with
no service function signature, no `.add()`/`.flush()`/`.commit()`/
`.get()` call site anywhere needing to change. An AST-based scan
(`scripts/classify_tenant_db_usage.py`, throwaway) classified every one
of 163 `Depends(get_db)` call sites across all 25 routers by whether an
`AuthContext`/`organisation_id` dependency shared the same function
signature: 151 converted, 12 genuinely stayed on `get_db` — all of
`auth/router.py` (signup/login/MFA, no org context yet by definition),
`platform/router.py`'s `/plans` catalog and Stripe webhook, and
`organisations/router.py`'s invitation-lookup/accept (a visitor
following a link has no membership yet either).

Actually wiring this in — not just making it compile — surfaced four
more real, previously-invisible bugs, each only reachable once a
request actually tried to exercise RLS for real for the first time:

1. `TenantScopedSession` used `set_config(..., is_local=true)` —
   transaction-scoped, matching `SET LOCAL`'s own semantics. This
   codebase commits mid-request in several places (e.g.
   `development/router.py`'s `add_property`: `db.commit()` then
   `db.refresh(prop)`) — the instant that first commit runs, the
   tenant context resets, and the next query silently has none again.
   Fixed by switching to `is_local=false` (connection-scoped, survives
   the rest of the request's connection checkout) — which immediately
   raises the pooled-connection question below.
2. A connection-scoped setting outlives the request that set it,
   because connection pooling means a *later, unrelated* request can
   be handed that same physical connection next — without an explicit
   reset, one request's organisation_id would leak into whichever
   request reuses its connection. Fixed with a `"reset"` pool-event
   listener (`app/core/db.py`) that runs `RESET app.current_org_id` on
   every connection checkin, for every connection, the same way a
   connection pool should never leak any other kind of per-request
   state. (Caught a second bug building this: `RESET` runs inside
   whatever transaction is already open at checkin time, not as an
   autocommitted statement — the listener's `RESET` silently had zero
   effect until an explicit `dbapi_connection.commit()` was added
   right after it; confirmed by hand before and after.)
3. Signup and accept-invitation both write rows into RLS-protected
   tables (`workspaces`, `subscriptions`, `memberships`,
   `audit_events`) through a deliberately unscoped `get_db` session —
   correct, since neither flow has an established tenant context yet
   (signup is creating the org; accept-invitation's caller has no
   membership yet either). But both bugs are the literal "chicken and
   egg" RLS problem: no context means every one of those inserts hits
   "new row violates row-level security policy", for real, the first
   time either flow ever ran against real Postgres. Fixed by scoping to
   the organisation (signup: right after the new `Organisation` row is
   flushed and has a real id; accept-invitation: to the already-
   existing `invitation.organisation_id`) before writing anything else
   in the same transaction.
4. The same bootstrap problem, one level more fundamental: `get_auth_
   context` itself — the function that resolves `ctx.organisation_id`
   for literally every authenticated, org-scoped request — queried the
   RLS-protected `memberships` table with no tenant context, because it
   *is* the function that was supposed to establish one. This meant no
   authenticated, org-scoped request could ever have succeeded against
   real Postgres, full stop — every single one would 403 immediately
   with "No active membership for this organisation", regardless of
   whether the membership genuinely existed. Fixed by scoping to the
   *claimed* `x_organisation_id` from the request header before running
   the membership check — safe, since that check is exactly what
   decides whether the claim is legitimate; RLS can only narrow what
   the existing `.filter(...)` already required, never widen it.
5. Stripe billing reads subscriptions through the same RLS-blocked
   pattern in two places: the webhook handler's
   `_find_subscription_by_organisation_id` (silently returns `None` for
   a real, matching subscription — webhook processing looks like it
   succeeds while doing nothing) and `_get_subscription_row` (opens its
   *own* fresh, separately-unscoped `SessionLocal()`, bypassing
   whatever tenant context the calling request's own session already
   had — `create_billing_portal_session` would reject a genuinely
   active customer as "no billing customer yet"). Both fixed by scoping
   to the already-known `organisation_id` (parsed from the webhook
   payload, or passed in directly) before querying.
6. The background worker's three jobs (`run_attention_scan_for_all_
   organisations`, `process_pending_report_jobs`,
   `process_pending_import_jobs`) all poll across every organisation in
   one tick — by design, there's no single org to scope the whole call
   to. Their job-discovery queries hit RLS-protected tables
   (`attention_rules`/`attention_signals`/`repairs`/`hazards`/... for
   the scan; `report_jobs`/`import_jobs` for the other two) with no
   context at all. Before this fix, **report generation and CSV import
   processing had never actually worked against real Postgres** — every
   report would sit `PENDING`, every upload `MAPPED`, forever, with no
   error anywhere, because the worker's own "find pending work" query
   silently returned nothing every tick, for every organisation. Fixed
   the same way in all three: list organisations first (`organisations`
   itself carries no RLS policy, so this query was always safe), then
   scope to each in turn before querying that org's own share of the
   work — report/import jobs gained an explicit per-org loop
   (previously one global query); the attention scan already had one,
   it just never scoped inside it.

`app/tests/test_rls_postgres.py` grew from 3 tests to 6, including two
that exist specifically because they failed first and caught real bugs
above, not because they were planned: `test_rls_context_does_not_leak_
to_a_connection_reused_by_a_different_org` (bug 2) and `test_a_real_
api_request_through_a_real_router_is_rls_scoped` (bugs 3/4, driving two
real signups and a real POST through `add_property` end to end) plus
`test_report_worker_processes_a_job_created_through_a_real_request`
(bug 6 — a real report request via HTTP, then the real worker function
run directly against the same database, asserting it actually reaches
`READY`). Full 380-test SQLite suite and all 30 Playwright specs still
pass unaffected — every fix here is additive/corrective to the
Postgres-only code path, gated the same way `TenantScopedSession`
already was.

**Post-Sprint-24 — a real backup/restore drill, closing STATUS.md's
other long-standing "no real Postgres to drill against" gap — and, in
verifying it properly rather than trusting a clean exit code, two more
real bugs found.** Seeded both fictional demo organisations
(`scripts/seed_demo.py`, run for the first time ever against real
Postgres — every development/building/property/component/repair/
compliance domain/hazard/lease/payment it creates, plus two real
Attention Engine scans, all went through the real API, all genuinely
RLS-scoped) end to end, then: `pg_dump -Fc` a real logical backup,
`DROP DATABASE` to genuinely destroy it (not simulated — the user
confirmed this explicitly, since dropping a database is a correctly-
classifier-blocked destructive action even for a local throwaway test
DB), `CREATE DATABASE` fresh, `pg_restore` from the backup. Verified,
not assumed: identical row counts across every table checked
(properties, developments, leases, repairs, attention_signals,
memberships, organisations), both organisation names intact, all 50
RLS policies restored, the `datalume` role still correctly non-
superuser (RLS stays enforced post-restore, not silently defeated) —
and the *real application*, not just raw SQL, signing in and reading
real org-scoped data back out correctly afterward.

Two more bugs surfaced doing this properly:

7. `scripts/seed_demo.py`'s own `ensure_org_and_owner` creates the org/
   workspace/membership rows the same deliberately-unscoped way
   signup's real endpoint used to (bug 3 above) — same chicken-and-egg
   fix, scoping to `org.id` once it's known, applied here too (this
   script predates the signup fix and was never updated alongside it).
8. The real app run this way caught something the earlier single-
   request/sequential-in-one-test RLS tests hadn't: `TenantScopedSession`'s
   connection-scoped `set_config` only holds if the *same* request keeps
   the *same* physical connection throughout — true by luck under low
   pool contention (a lone test creating one property), false under
   the seed script's busier, multi-request-per-org pattern. A plain
   `sessionmaker(bind=engine)` session releases its connection back to
   the pool on every commit and may be handed a *different* one on the
   next query — exactly what `add_development`'s `db.commit()` then
   `db.refresh(dev)` hit. Fixed properly this time, not by luck: `app/
   core/db.py`'s `SessionLocal` now explicitly holds one `Connection`
   for the Session's whole life (`_RequestSession`, replacing the plain
   `sessionmaker`) rather than letting SQLAlchemy silently swap
   connections between transactions — the fix lives in the one shared
   factory every caller (`get_db`, the worker, the seed script, Stripe
   billing) already goes through, not something each call site needs
   to know about. `close()` releases the held connection itself, which
   is what lets the existing `"reset"` pool-event listener still do its
   job on checkin. A new regression test,
   `test_many_sequential_requests_each_commit_and_refresh_correctly`,
   exists specifically because a single-request test alone would not
   reliably have caught this — it has to create several things in a row
   against the same org, the way the seed script actually did, to force
   the same connection-reuse condition under real (if light) pool
   contention.

**One more real, structurally different bug found via this drill's own
after-the-fact verification — closed the same day, once asked for.**
`GET /api/v1/auth/me` (`app/auth/router.py`) queries `memberships`
filtered by `user_id` alone, deliberately spanning every organisation
the signed-in user belongs to — the workspace-switcher list.
`memberships` is RLS-protected, and there is no single organisation to
scope this query to; scoping it to any one org would make the user's
*other* orgs disappear from their own switcher. Post-restore, logging
in via the real demo credentials and calling the real `/me` endpoint
returned `memberships: []` even though both the row and a correctly-
scoped `GET /api/v1/properties` for that same org worked fine —
proving the backup/restore itself was sound and isolating this as a
separate, genuine gap. Same underlying shape as the worker jobs
finding earlier in this stretch (a legitimate cross-tenant access
pattern RLS-as-designed doesn't support) but worse there: the worker
can reasonably loop over every organisation once a day, but `/me` runs
on every login and page load, so "loop over every org in the system
checking membership" doesn't scale here the way it does for a nightly
job.

Fixed without a new Postgres role or deployment credential: migration
`0027_memberships_own_rows_visible` widens `memberships`' own RLS
policy with `OR user_id = current_setting('app.current_user_id',
true)::uuid`, and `app/core/tenancy.py`'s `get_current_user` now sets
that second session variable (same connection-scoped `set_config`
pattern as `app.current_org_id`, same `"reset"` pool-event listener
clearing it on checkin) the moment a session cookie resolves to a real
user — before any organisation is chosen, exactly when `/me` runs. A
user's own membership rows become visible regardless of org context
without weakening anything: `organisations/router.py`'s `list_members`
(an org's own roster) stays additionally filtered by `organisation_id`
at the app layer exactly as before, so the OR clause can only ever add
visibility for the asking user's *own* rows, never let one org see
another's roster.

New test `test_me_shows_a_users_own_memberships_without_leaking_
anyone_elses` proves both directions against real Postgres: two real
users, two real orgs — each user's own `/me` shows exactly their own
org (the bug, now fixed) and neither user's membership row ever
appears in the other's data, including the other org's own member
roster (the risk a careless fix could have introduced).
`app/tests/test_rls_postgres.py` is now 8 tests; full 380-test SQLite
suite, migration downgrade/upgrade round-trip, and offline
`alembic upgrade head --sql` validation all still pass.

**Post-Sprint-24 — a genuine concurrency test, and five real race
conditions it found that no sequential test (today's or any earlier
sprint's) could have caught.** Every RLS test above — even the
sequential-commits regression test — only ever has one request in
flight at a time, which is exactly the condition under which a
concurrency bug can pass by luck. `test_concurrent_requests_from_
different_organisations_never_cross_contaminate` closes that gap for
real: 10 independent `TestClient` instances (their own cookie jars,
their own signups, their own orgs — not one client reused across
threads, which would just serialize on its own internal state rather
than genuinely contend for the connection pool), each hammering the
same small pool (`pool_size=5` by default) at the same moment via real
Python threads, each creating and re-reading its own property five
times, asserting zero cross-contamination throughout. Needs real Redis
alongside real Postgres — a thread's own signup/login needs genuinely
working concurrent session storage, not a shared dict whose thread-
safety would be beside the point either way — so this one test skips
unless `REDIS_URL` is also set; CI's `rls` job now runs a `redis:7`
service container alongside `postgres:16` specifically for it.

First run found a real `UniqueViolation` race, not a test artifact:
`get_or_create_plan` (`app/platform/billing.py`) and `_get_or_create_
role` (`app/auth/router.py`) — both lazy "seed this global row the
first time anyone needs it" functions, both called from signup — use a
plain check-then-insert with no race protection, even though this
exact codebase already has the *correct*, established pattern for this
shape (`db.begin_nested()` + catch `IntegrityError` + re-read the
winner's row) in three other places (`app/attention/service.py`'s
`get_or_create_rule`, `app/identifiers/service.py`'s own documented
`_get_or_create_pattern`). `billing.py`'s own docstring even claimed
parity with `_get_or_create_role` ("same lazy-upsert pattern as system
roles") — neither actually had the protection. Fixed both the same
way the established pattern already does it.

Checking every other "get or create a global row" function in the
codebase for the same shape (not waiting for the test to find each one
the hard way) found two more, worse in one way: `get_or_create_global_
component_type` (`app/development/component_types.py`) and
`get_or_create_default_framework`/`ensure_compliance_catalog_seeded`
(`app/operations/compliance/seed.py`) had no unique constraint on the
underlying table at all — `component_types`/`compliance_frameworks`/
`compliance_domains` were never given one, so the race wouldn't have
raised an error, it would have silently created duplicate global
catalog rows (two "BOILERS" component types, etc.) with no error
anywhere to notice by. Migration `0028_global_seed_unique_constraints`
adds the missing partial unique indexes (`WHERE organisation_id IS
NULL` — the global seeded catalog needs unique codes/names among
itself, but a per-organisation custom addition, e.g. an unrecognised
component type auto-created during CSV import, stays free to reuse a
code another org or the global catalog already uses), and both
functions now use the same `begin_nested`/`IntegrityError` pattern as
everywhere else.

Confirmed fixed, not just plausible: the concurrency test failed
reproducibly (7 of 10 workers) against a fresh database before these
fixes, and passes reliably across repeated fresh-database runs after
them. Full 380-test SQLite suite, the 9-test Postgres RLS suite,
migration downgrade/upgrade round-trip, and offline
`alembic upgrade head --sql` validation all green.

**The narrower, per-organisation instances of the same pattern —
closed the same day, the dedicated pass promised above.** Migration
`0029_per_org_config_unique_constraints` adds the unique constraint
each of these seven tables was always missing —
`handover_readiness_check_weights`/`planned_investment_weights`/
`repair_rule_configs`/`hazard_rule_configs` on `(organisation_id,
<code column>)`, and the three true per-org singletons
(`planned_investment_configs`/`compliance_status_configs`/
`payment_reconciliation_configs`) on `organisation_id` alone — and,
unlike migration 0028's global-catalog constraints (Postgres-only
partial indexes with no SQLite equivalent), these are plain, fully
portable constraints declared on the ORM models themselves too
(`__table_args__ = (UniqueConstraint(...),)`, same convention
`Plan.code`/`Role.code` already used), so SQLite's own test metadata
now matches the real schema instead of silently diverging from it.

All seven `get_or_create_*` functions (`app/development/service.py`'s
`get_or_create_handover_readiness_weight`/`get_or_create_planned_
investment_weight`/`get_or_create_planned_investment_config`,
`app/operations/service.py`'s `get_or_create_repair_rule_config`,
`app/operations/compliance/service.py`'s `get_or_create_status_
config`, `app/operations/hazards/service.py`'s `get_or_create_hazard_
rule_config`, `app/commercial/service.py`'s `get_or_create_
reconciliation_config`) already used `.with_for_update()` — which,
worth noting explicitly, only locks a row that *already exists* and
does nothing for the actual race (two concurrent first-ever calls can
both find nothing to lock and both attempt the insert) — now also wrap
that insert in the same `begin_nested`/`IntegrityError`/re-read pattern
as everywhere else. Verified against real Postgres: the normal,
non-racing path (sign up, read a config, read it again) still returns
the exact same row on repeat calls, not a duplicate.

`app/development/component_types.py`'s `get_or_create_org_component_
type` is the one function in the original list of eight left
genuinely unfixed, not just deferred by oversight: it matches by
fuzzy, case-insensitive, singular/plural-tolerant *name* (CSV import
resolving free-text like "Boiler" against "Boilers"), not a clean
exact-code lookup the other seven share — a correct fix needs a
differently-shaped constraint (on a normalised name, not the raw
`code` a name gets transformed into) and more thought than a
mechanical application of the established pattern deserves. Still
real, still narrow (two concurrent CSV imports creating a near-
identical custom type name for the same org), left open deliberately.

Full 380-test SQLite suite (now genuinely exercising these constraints
too, not just the Postgres-only ones), the 9-test Postgres RLS suite,
migration downgrade/upgrade round-trip, and offline
`alembic upgrade head --sql` validation all green.

**Post-Sprint-24 — the one remaining get_or_create race, half-closed
honestly rather than left alone or oversold.** Migration
`0030_org_component_type_unique_constraint` adds `UNIQUE
(organisation_id, code)` to `component_types` — a plain constraint,
not a partial index like migration 0028's global-catalog one, because
SQL's NULL-is-never-equal-to-NULL semantics mean it naturally only
ever constrains the non-NULL-`organisation_id` (per-org custom) rows
against each other, coexisting without conflict alongside 0028's own
partial index on the disjoint (global, `organisation_id IS NULL`)
subset of the same table. `get_or_create_org_component_type`
(`app/development/component_types.py`) now wraps its insert in the
same `begin_nested`/`IntegrityError` pattern as everywhere else,
re-matching via the function's own `find_component_type_by_name` on
collision (consistent with how the winner was going to be found
anyway).

This closes the case that actually matters most in practice — two
concurrent CSV import rows for the same org referencing the exact same
new type name, where `code` is a deterministic function of `name` so
both calls would derive the identical code and now genuinely collide.
It deliberately does **not** close the narrower case `find_
component_type_by_name`'s own fuzzy, singular/plural-tolerant matching
exists for in the first place: two concurrent imports of e.g. "Boiler"
and "Boilers" for the same org derive different codes (`BOILER` vs
`BOILERS`) that a database constraint has no way to recognise as the
same thing — the fuzzy equivalence lives only in the Python matching
logic, not the schema. A real fix for that half would need a
normalised-form constraint (or matching on something other than the
raw derived code), which is a genuine design decision, not a
mechanical application of the pattern used for the other eight —
documented honestly rather than quietly treated as covered by this
commit's own test coverage.

Verified against real Postgres: calling the function twice with the
exact same new name returns the same row both times, not a duplicate.
Full 380-test SQLite suite, the 9-test Postgres RLS suite, the
ingestion/component test files specifically (the real CSV-import code
path this function serves), migration downgrade/upgrade round-trip,
and offline `alembic upgrade head --sql` validation all green.

With this, every `get_or_create_*`-shaped race this session's own
concurrency test and the subsequent audit found is either closed or
has an honestly-documented reason it's only partially closed — nothing
left silently assumed fixed.

**Real load testing against Postgres-backed infra — spec §72, closed
with real measurements rather than asserted.** Spec §72 names required
techniques (pagination, server filtering, indexes, aggregation,
caching, background jobs) but gives no specific latency number, so the
approach was: audit every `list_*` endpoint for the named mechanisms,
fix what was mechanically missing, then prove it with a real
large-volume seed rather than guess.

Audited all ~23 `list_*`/collection endpoints by grep for an existing
`limit:` parameter. Four were completely unpaginated despite serving
exactly the entity types spec §72 names as needing it at scale:
`GET /api/v1/repairs`, `GET /api/v1/payments`, `GET
/api/v1/rent-obligations`, and `GET /api/v1/documents`. All four now
take `limit`/`offset` (default 100, capped at 500) following the same
pattern `list_properties`/`list_components` already used — see
`app/operations/repairs_router.py`, `app/commercial/router.py` (two
endpoints), `app/commercial/service.py`'s `list_rent_obligations`, and
`app/documents/router.py`.

Separately, `get_portfolio_summary` (`app/development/portfolio.py`) —
the home dashboard summary, hit on every login — loaded every property
in the org into Python just to compute a count and a status breakdown.
Rewritten to two SQL aggregates (`count()` and `GROUP BY status`); no
business logic involved, so this one was safe to fix immediately
rather than defer.

Then seeded a real organisation directly via SQL (bypassing the ORM —
this is a volume-generation shortcut, not a correctness test; insert-
path correctness is already covered everywhere else) with **20,000
properties and 200,000 repairs**, correctly FK'd and provenance-
stamped, and measured real endpoint latency through the actual
FastAPI app against real Postgres (`scripts/load_test.py`, kept for
whoever next needs to re-check or extend this). Results:

- `GET /api/v1/properties`: ~15-20ms flat regardless of offset — its
  existing `organisation_id` index and a comparatively small
  20,000-row table are enough on their own, no new index needed.
- `GET /api/v1/repairs` degraded with page depth even after being
  paginated: ~65ms at offset 0 vs ~104ms at a deep offset (199,000, on
  a 200,000-row table) — the existing `organisation_id`-only index
  found the org's rows, but Postgres still had to sort all 200,000 of
  them by `reported_date` from scratch before slicing. Added
  `(organisation_id, <date column> DESC)` composite indexes for all
  four of the endpoints just paginated (`repairs.reported_date`,
  `payment_transactions.received_date`, `documents.uploaded_at`,
  `rent_obligations.due_date`) in migration
  `0031_list_endpoint_sort_indexes`. Re-measured with a controlled A/B
  (same script and org, index dropped via `alembic downgrade` then
  restored, isolating the index's real effect from other variance):
  - Offset 0 (the common case — first page): ~31ms -> ~6ms, a real
    ~5x improvement, since Postgres now reads rows already in sorted
    order instead of sorting the whole table first.
  - A deep offset (199,000): ~67ms -> ~60ms, only a modest gain —
    Postgres still has to walk and discard ~199,000 index entries
    before reaching the requested page; the index removes the sort
    step but not the `OFFSET` walk itself. Real constant-time deep
    pagination needs keyset/cursor-based pagination instead of
    `OFFSET`/`LIMIT`, which is an API shape change, not an index —
    left as a documented limitation rather than fixed here, since the
    product's actual usage pattern is shallow pages (recent repairs),
    not browsing to page 2,000.
- ~~`GET /api/v1/portfolio/summary`: **~3.6 seconds**~~ **Fixed** — see
  the dedicated entry below. Even after the properties aggregation was
  rewritten to SQL, this was tracked down to `run_data_health_checks`
  (`app/data_health/rules.py`), which the dashboard also calls: 14
  separate check functions, several of which independently re-ran
  `db.query(Property)...all()` or `db.query(Component)...all()` for
  the same org — the same full-table-into-Python pattern, repeated
  many times over rather than once.
- ~~`GET /api/v1/repairs/intelligence`~~ **Fixed** — see the dedicated
  entry below. Originally measured at **~11.4 seconds** at 200,000
  repairs (`app/operations/repairs_intelligence.py`) — loaded every
  repair for the org into Python and computed open/completed/emergency
  counts, category and contractor breakdowns, average completion time,
  and repeat-repair/repeat-failure signals all in Python via `Counter`,
  the latter by calling the single-entity repeat-repair/repeat-failure
  functions once per distinct property/component.

Full 380-test SQLite suite, the Postgres RLS suite, the Playwright E2E
suite, migration downgrade/upgrade round-trip, and offline `alembic
upgrade head --sql` validation all green on the pagination/index
changes.

**Load testing, follow-up — the two remaining suspected Python-
aggregation endpoints measured instead of left on suspicion**
(`scripts/load_test_part2.py`, reusing the same seeded org):

- ~~`GET /api/v1/defects/intelligence`~~ **Fixed** — see the dedicated
  entry below. Originally measured at **~670ms** at 40,000 defects
  (20,000 properties x 2 each); same full-table-into-Python-`Counter`
  shape as `repairs_intelligence`, just a smaller table and lighter
  per-row work (no repeat-failure signal), hence the much smaller
  number than that endpoint's 11.4s at 200,000 rows. Unlike
  `repairs_intelligence`'s repeat-repair detection, every number this
  endpoint returns is a deterministic count/sum/average with no fuzzy
  matching or time-windowed business logic — so it turned out to be a
  mechanical SQL rewrite, not a risky one.
- ~~`GET /api/v1/compliance/assurance-report`~~ **Fixed** — see the
  dedicated entry below. It was a different and more severe shape than
  the other three: `get_board_assurance_report` called
  `compliance_status()` once per applicable `(entity, requirement)`
  pair, and `compliance_status()` itself ran 3-4 queries per call
  (status config, current applicability, latest inspection, open
  actions) — an O(pairs) count of individual ORM round trips, not one
  big table load, and the only one of the four that got
  *categorically* worse (not just linearly slower) as both properties
  and requirements-per-property grew. Unlike `data_health`'s 14
  check functions or `repairs_intelligence`'s repeat-repair detection,
  this one's fix was mechanical rather than a business-logic rewrite —
  see below.
- ~~`commercial/arrears.py`'s `arrears_for_lease` and `collection_rate`~~
  **Fixed** — see the dedicated entry below. Originally read but
  deliberately not included in the first measurement pass: both are
  naturally bounded differently from the other four (`arrears_for_
  lease` filters to one lease, `collection_rate` filters to a date
  period, neither an unbounded org-wide scan), so this was N+1 against
  a bounded N, not the same category of problem — still worth fixing
  since it was easy and safe, just not as urgent.

**`get_board_assurance_report`'s N+1 fixed — a mechanical bulk-fetch,
not a business-logic rewrite, and load-tested at full scale.**
Unlike `data_health`/`repairs_intelligence` (at the time this was
written — `repairs_intelligence` was fixed later the same session,
see its own dedicated entry below), this one's per-pair cost wasn't
one big Python aggregation needing new
business logic — `status_engine.py` already separated the decision
logic (`_resolve_status`, now exported as `resolve_compliance_status`
since it's shared across modules) from the data it needs, so the real
fix was just changing *how* that data gets fetched for a portfolio-
wide report: once per report instead of once per pair.

`app/operations/compliance/assurance.py` now, before the loop:
fetches the org's `ComplianceStatusConfig` once (was: once per pair,
via `compliance_status()`'s own internal call); uses each
`RequirementApplicability` row directly as its own "current
applicability" (it already satisfies every filter the per-pair lookup
would apply — same org/entity/requirement, same applicable_from/
applicable_to window the outer query already filtered on — so this
isn't just faster, it's also strictly more correct than the old
per-pair re-query in the edge case of overlapping applicability
periods, which could pick an arbitrary one); and bulk-fetches every
`Inspection` and open `ComplianceAction` for the entities/requirements
actually appearing in the report in two queries total, grouping them
in Python by `(entity_type, entity_id, requirement_id)`. The loop then
calls the same pure `resolve_compliance_status()` function every other
caller uses, just fed from these pre-built dicts instead of a fresh
query per pair — identical decision logic, zero behaviour change,
only the data-fetching shape changed.

Measured with `scripts/load_test_part2.py` against the same seeded
org, before/after:

- At 2,000 applicability pairs (measured pre-fix): ~1.58s.
- At the full 20,000 pairs (one requirement per every seeded
  property) — previously only a ~15.8s linear projection, now measured
  directly because the fix makes that tractable: **~440ms**, roughly
  **35x faster** than the pre-fix number at the same 2,000-pair scale
  would scale to, and comfortably fast at the full portfolio size the
  projection warned about.

Full 380-test SQLite suite, the dedicated `test_assurance_report.py`/
`test_reports.py`/compliance test files (51 tests), and the Postgres
RLS suite all green.

**`commercial/arrears.py`'s bounded-N N+1 fixed too, same mechanical
bulk-fetch pattern.** `matched_amount_for_obligation`
(`app/commercial/service.py`) was a single-obligation query, called
once per obligation in a loop by both `arrears_for_lease` and
`collection_rate`. Added `matched_amounts_for_obligations` — the same
function, batched: one query for every obligation ID passed in,
grouped into a `dict[obligation_id, matched_pence]` by Python — and
both callers now build that dict once before their loop instead of
querying inside it. No decision logic changed, same as the board
assurance fix.

Load-tested with a new `scripts/load_test_part3.py` (seeds 5,000
leases and 15,000 rent obligations/payment allocations for the same
org, due within one quarter — the shape `collection_rate`'s own
org-wide date-range query actually hits): a clean before/after (code
stashed via `git stash`, measured, restored, re-measured, against the
exact same seeded data) showed `GET /api/v1/collection-rate` dropping
from **~4.2s to ~340ms** at 15,000 obligations — about **12x faster**
— with the computed collection rate (0.7) identical before and after,
confirming the fix changed performance, not behaviour.

Full 380-test SQLite suite and the Postgres RLS suite green.

**`get_defects_intelligence` rewritten to SQL — reassessed as safe
once actually read closely, not just assumed risky by category.**
Re-reading `app/development/defects_intelligence.py` line by line
(rather than lumping it in with `data_health`/`repairs_intelligence`
by shape alone) showed every number it returns — open/overdue/
warranty-related counts, cost sums, per-contractor/category/component-
type breakdowns, the repeat-category signal — is a deterministic
count, sum, or average with no fuzzy string matching and no
configurable, time-windowed business rule the way
`repairs_intelligence`'s repeat-repair detection or `data_health`'s
address-normalisation check have. That made it a safe, mechanical
rewrite, not a risky one, despite living in the same "load everything
into Python" category as the other two.

Rewritten to real SQL aggregation: `COUNT`/`GROUP BY` for every count
and breakdown, `SUM` for the cost totals, a `HAVING`-shaped subquery
(group by location+category, keep groups with more than one defect,
count per category) for the repeat-category signal. Two deliberate
exceptions, both documented inline: `by_component_type` still counts
*distinct affected components* per type rather than *defects* per
type, preserving an existing quirk in the original Python
implementation exactly rather than silently changing it while
rewriting; and `average_resolution_days` stays a Python computation
fed by a narrow two-column projection (`reported_date`,
`completion_date` only, not full rows) rather than a SQL date-diff,
since `completion_date - reported_date` isn't portable the same way
across SQLite (this codebase's test dialect) and Postgres
(production) — a case where keeping one small piece in Python was the
more honest choice than forcing SQL portability that doesn't really
exist.

Load-tested the same way as the other two fixes: `git stash` on the
same seeded 40,000-defect org, measured before, restored, measured
again. **~682ms -> ~110ms, about 6x faster.** The existing
`test_defects_intelligence_aggregates` test (exact small-scale
assertions, not just a smoke check) passed unchanged, confirming the
rewrite preserves behaviour, not just improves speed.

Full 380-test SQLite suite and the Postgres RLS suite green.

**`get_repairs_intelligence` rewritten too — the last of the three,
and the biggest win of any fix this session, found by actually
separating its two genuinely different halves instead of treating the
whole function as one risky block.** Its simple counts/breakdowns
(open/completed/emergency counts, category/contractor breakdowns, cost
totals) are exactly the same deterministic-aggregation shape as
`defects_intelligence` and were rewritten the same way, to `COUNT`/
`GROUP BY`/`SUM`. `average_completion_days` stays a narrow two-column
Python computation for the same SQLite/Postgres date-arithmetic
portability reason as the other two fixes.

The repeat-repair/repeat-failure signals were the genuinely riskier-
looking half — they fold in `repeat_repair.py`'s "N+ repairs within a
configured window" rule — but reading that module closely (rather
than assuming "business logic = don't touch") showed the actual
*decision rule* is a plain threshold comparison with no fuzzy matching
and no AI-adjacent logic at all; what made the original slow was
calling the single-entity `repeat_repairs_for_property`/`repeat_
failures_for_component` functions once per distinct property/
component, each re-fetching the org's rule config and re-querying
repairs scoped to just that one entity. `repeat_repair.py` itself is
untouched — those two functions keep being called per-entity by the
dedicated property/component endpoints, the attention engine, Ask
DataLume, and Planned Investment Intelligence, where there's a single
entity and no N+1 to begin with. `get_repairs_intelligence` instead
now fetches both rule configs once, bulk-queries repairs within the
wider of the two rule windows once, and groups them in Python by
property/component — same threshold-comparison decision rule, applied
to bulk-fetched data instead of N individual queries.

Added `test_repairs_intelligence_surfaces_repeat_signals`
(`app/tests/test_repairs.py`) — no existing test exercised
`repeat_repair_properties`/`repeat_failure_components` through the
intelligence endpoint itself, so this checks the bulk computation
lands on exactly the signal the single-entity functions would
produce for the same data (mirrors `test_repeat_repairs_for_property`/
`test_repeat_failures_for_component`'s own scenario).

Load-tested with a clean `git stash` before/after on the same seeded
20,000-property/200,000-repair organisation (repairs seeded 10 per
property, within the rule's 12-month window — a worst case where
every single property triggers the signal, not a sparse one):
**~56.7s -> ~840ms, roughly 67x faster** — the largest improvement of
any fix this session — correctly returning all 20,000 triggered
property signals (confirmed via the response body, not just the
timing) and zero component signals (this seed never sets
`component_id` on its repairs, so there's nothing to trigger there).

Full 381-test SQLite suite (the new test included) and the Postgres
RLS suite green.

**`run_data_health_checks` rewritten — the last of the four, and the
one that turned out to need the most care, since "14 functions" meant
14 separate correctness questions, not one.** Re-reading all 14 check
functions individually (rather than treating "14 functions, some do
fuzzy matching" as one risk category) showed the real picture: most
are plain existence/boolean checks (`IS NULL`, a date comparison, an
all-five-foreign-keys-unset test) with no behavioural subtlety at all;
a few need a "does this id appear in another table" membership test
(missing UPRN/serial number/stock survey/handover record); a few need
a real "GROUP BY, keep groups with more than one row" duplicate check
(components, external references, documents); and exactly one
(`check_stale_stock_condition_survey`) needs "the latest row per
property," which both SQLite and Postgres support identically via
`ROW_NUMBER() OVER(...)` — no portability concern there either.

Only `check_duplicate_properties`' address matching turned out to have
a genuine, if narrow, portability snag: `_normalize_address` collapses
*internal* whitespace runs, not just leading/trailing, which Postgres
can do with `regexp_replace` but SQLite (this codebase's test dialect)
can't without a loaded extension. Rather than force a regex into one
dialect or silently drop the whitespace-collapse behaviour, that one
check still normalises in Python — fed by a narrow
`(id, reference, address)` projection instead of full `Property` rows,
same "SQL where portable, narrow Python projection where it genuinely
isn't" pattern the date-arithmetic pieces of the two Intelligence
fixes already used. `check_duplicate_components`'s very similar-
looking manufacturer/model matching has no such snag — `LOWER`/`TRIM`/
`COALESCE` are portable, so that one *is* real SQL, computed via
`GROUP BY` on those exact expressions instead of a Python `key()`
function per row.

Every rewrite was verified three ways: the existing
`test_data_health.py` suite (14 tests, several asserting exact
`applicable_count`/`failing_count`/`affected_entity_id` values, not
just "didn't crash") passed unchanged on SQLite; a separate direct
check against **real Postgres** (signing up a fresh org via
`TestClient` and exercising duplicate properties with irregular
whitespace, duplicate components with irregular case/whitespace in
manufacturer/model, a stale-vs-current survey pair for the same
property, conflicting external references, and duplicate documents)
confirmed every one of the trickier rewrites — especially the window-
function "latest survey" and the two normalisation-dependent duplicate
checks — produces the exact right answer on the dialect that actually
matters in production, not just the dialect the test suite happens to
run on; and the load test below.

Load-tested with a clean `git stash` before/after on the same seeded
20,000-property organisation, measured two ways:

- **Raw query/aggregation time** (calling the 14 rule functions
  directly, bypassing the API layer): **~1,400ms -> ~171ms, about 8x
  faster** — this is the actual "load everything into Python" cost
  this rewrite targeted, and the number directly comparable to the
  other three fixes.
- **The full `GET /api/v1/data-health` endpoint**, at a realistic
  90%-data-coverage seed (18,000 of 20,000 properties have a UPRN and
  a stock condition survey on file, 2,000 genuinely don't — not the
  property-count-sized worst case the raw profiling above used, where
  *every* property fails *every* check at once): **~2,716ms ->
  ~645ms, about 4.2x faster**, with identical output both times (4,000
  findings, score 98.6% either way) confirming the rewrite changed
  speed, not behaviour.

The gap between the 8x raw-query win and the 4.2x end-to-end win is a
real, separate, newly-surfaced finding, not a flaw in this rewrite:
`run_data_health_checks` persists one `DataHealthFinding` row per
finding via a `db.add()` loop, and `get_data_health`
(`app/data_health/router.py`) returns every one of them in the
response body — at the realistic 4,000-finding scale this costs real
time (insert + Pydantic serialisation of 4,000 objects) *in addition
to* the query time this rewrite fixed, and at the degenerate
100%-failure-rate scale used for raw profiling (40,000 findings) it
would dominate completely. This is a different architectural question
from "Python aggregation vs SQL" — bulk/Core-level insert instead of
one `db.add()` per row, and/or paginating the findings response — and
is **not fixed here**, flagged for whoever next finds Data Health
slow at a very high finding count.

Full 381-test SQLite suite and the Postgres RLS suite green.

## Not yet done

Sprint 24 closed out the roadmap's stated 24 sprints. What's left is
what Sprint 24 itself found couldn't be done for real in this sandbox,
plus what earlier sprints already flagged — not a "next sprint," a
punch list for whoever takes this toward a real pilot:

- ~~RLS is correctly designed but not actually active on any real
  request (get_tenant_db unused by all 25 routers).~~ **Closed** — see
  the dedicated entry below. `get_tenant_db` is now wired into every
  tenant-scoped router, and both layers of architecture 01 §1's tenant
  isolation are genuinely active and proven end to end, not just
  app-layer alone.
- ~~Seven per-organisation get_or_create_* functions share the same
  unprotected check-then-insert race as the global ones a concurrency
  test found.~~ **Closed** — see the dedicated migration
  `0029_per_org_config_unique_constraints` entry above.
- ~~get_or_create_org_component_type matches by fuzzy name, needs a
  differently-shaped fix.~~ **The exact-duplicate half closed** — see
  migration `0030_org_component_type_unique_constraint` above. Two
  concurrent imports of the exact same new type name for the same org
  now collide for real and resolve correctly. The narrower singular/
  plural-variant case (e.g. "Boiler" vs "Boilers" racing for the same
  org) stays open on purpose — a database constraint can't encode that
  fuzzy equivalence, only exact-code duplication, and the honest fix
  (match on a normalised form, not raw derived code) needs more design
  than this mechanical pass.
- ~~Real load testing against Postgres-backed infra~~ **Closed** — see
  the dedicated entry above. Four previously-unpaginated list
  endpoints (repairs, payments, rent obligations, documents) fixed,
  measured against a real 20,000-property/200,000-repair seed, and a
  composite-index migration added once the deep-offset cost was
  actually measured rather than assumed.
- ~~Every "intelligence"/"summary" endpoint this session's load
  testing flagged as aggregating in Python instead of SQL~~ **All
  fixed.** `get_board_assurance_report`, `commercial/arrears.py`'s two
  functions, `get_defects_intelligence`, `get_repairs_intelligence`,
  and `run_data_health_checks` (see each one's own dedicated entry
  above) all turned out, on close individual reading rather than
  being judged by category, to be mechanical rewrites with no
  behaviour-changing business-logic risk once actually read line by
  line.
- ~~`run_data_health_checks` persists one row per finding with no bulk
  insert or pagination~~ **The bulk-insert half genuinely closed, the
  pagination half only partial — documented honestly rather than
  claimed as fully fixed.** `run_data_health_checks`
  (`app/data_health/rules.py`) now replaces the per-row `db.add()`
  loop with a single `sqlalchemy.insert(DataHealthFinding)` Core
  statement. Measured directly (isolated from everything else, same
  SQLite session either way): **~125ms -> ~32ms at 4,000 findings
  (3.9x), ~1,123ms -> ~283ms at 40,000 (4.0x)** — a real, unconditional
  win, since this step runs on every call regardless of pagination.
  `GET /api/v1/data-health` also gained `limit`/`offset` query params
  (`findings_total` added to the response so a paginated caller still
  knows the real count) — but measured against real Postgres at
  80,000 findings, `?limit=100` took **~1,913ms vs ~2,060ms
  unpaginated — only ~7% faster, not the "fast regardless of total
  count" result pagination delivered for repairs/payments/documents
  elsewhere in this file.** The reason: `limit`/`offset` slice the
  Python list *after* `run_data_health_checks` has already evaluated
  every check, built every `Finding` object, and (now efficiently, but
  still unconditionally) bulk-inserted every row — the same "computed
  fresh on every read, nothing persisted to go stale" design this
  codebase uses for Data Health/Handover Readiness/every repeat-signal
  engine, which this fix correctly left alone rather than quietly
  changing. Genuinely paginating a *read* of already-computed findings
  (as opposed to the Pydantic response list) would mean serving
  `DataHealthFinding` rows straight from the table instead of
  recomputing-then-slicing on every call — a real architectural
  change to that "never stale" guarantee, not a pagination-parameter
  fix, and out of scope here. Full 382-test SQLite suite (the new
  pagination test included) and the Postgres RLS suite green.
- ~~A real backup drill~~ **The Postgres half closed** — see the
  dedicated entry above: real `pg_dump`/`DROP DATABASE`/`pg_restore`
  against real seeded demo data, verified (not assumed) down to row
  counts, RLS policies, and role permissions, plus the real application
  reading it back correctly afterward. Architecture §5's *object-
  storage* versioning half stays open — that's genuinely Azure-side
  infra-managed tooling, not application code, and there's still no
  real cloud storage in this sandbox to drill against.
- ~~A genuine RLS gap found by the backup drill's own verification:
  GET /auth/me needs a user's memberships across every org they
  belong to.~~ **Closed** — see the dedicated migration
  `0027_memberships_own_rows_visible` entry above.
- **Full OTel/Sentry wiring to a real collector** — architecture §3
  names both; this sprint built the structured-logging half for real
  (see above) since it's independently valuable and fully verifiable
  here, but didn't add span-based tracing, since there's no real
  collector in this sandbox to send spans to and a half-wired tracer
  would be worse than a documented gap.
- ~~Lease events aren't monitored.~~ **Closed** — see the dedicated
  `LEASE_EVENT_UPCOMING` entry above. This was the last genuinely
  missing item in either spec §77 or §78; both acceptance tests are
  now fully REAL.
- **The Playwright E2E acceptance suite covers a real first slice, not
  the full 50 steps.** See the dedicated notes above for what exists
  now (auth, the Development->Building->Property golden thread, Ask
  DataLume's ungrounded-question guarantee, a compliance requirement
  against a seeded domain, commercial arrears, worker-driven report
  generation, a manual attention-engine scan that genuinely detects a
  repeat-repair pattern, a worker-driven CSV import going
  MAPPED -> IMPORTING -> COMPLETED, handover authorisation exercising
  the real below-threshold rejection and override-reason path, a
  defect's real server-validated status transition plus a warranty
  being added and voided, a change control request being approved and
  implemented against a specification, a component's real age *and*
  a real inspection driving every applicable factor of Planned
  Investment Intelligence, construction evidence genuinely linked to
  the exact component it belongs to, Property 360 showing a real
  development/building lineage and the readiness record persisting
  after handover, Ask DataLume answering a real, grounded question
  about a development, a lease's break date/rent review date/service
  charge being genuinely captured, a payment method round-tripping, an
  ambiguous payment being split across two obligations rather than just
  resolved against one, a rent obligations CSV import, Data Health
  score/findings, raising and completing a compliance action, hazard
  tracking plus a repeat damp & mould signal, a component-failure
  signal, a board-level report, and a repairs CSV import). Every item
  named in spec §77 (Housing Operations) and §78 (Commercial) has now
  been through the REAL/UI-GAP/TEST-GAP/MISSING audit and is REAL —
  except lease-event monitoring, genuinely missing (see the dedicated
  entry above), the one acceptance-test item in either list that still
  needs real design work rather than a quick form or test fix.
  ~~Generating a handover report was never actually a gap —
  `HANDOVER_READINESS` is a real, backend-tested report type that
  simply hasn't been given its own Playwright spec yet~~ **Closed, and
  so are the other two report types that had the same gap.** All 5
  report types (`app/reports/models.py`'s `ReportType` — `DEVELOPMENT_
  SUMMARY`, `BOARD_ASSURANCE`, `HANDOVER_READINESS`,
  `COMPLIANCE_EXECUTIVE_SUMMARY`, `COMMERCIAL_PORTFOLIO`) now have
  real E2E coverage: `apps/web/e2e/reports.spec.ts` carries Development
  Summary (original), Handover Readiness, Compliance Executive Summary,
  and Commercial Portfolio; `board-report.spec.ts` carries Board
  Assurance. Each follows the same worker-driven PENDING -> READY ->
  download shape; Compliance Executive Summary and Commercial
  Portfolio needed real supporting data first (a property; a lease +
  rent obligation within the report's own "current month to date"
  window, reusing `commercial-arrears.spec.ts`'s exact UI flow) for
  their content to be non-trivial, same as the others. All 33
  Playwright specs green. The 50-step acceptance suite as a whole
  still covers a real first slice, not every step named across spec
  §76-78 — this closes the reports-generation slice of it completely,
  not the whole list.
- ~~Spec §76 step 11, "Add floors," had a real backend (`POST`/`GET
  /api/v1/floors`) and UI (the building detail page's own "Add a
  floor" form) but no Playwright spec~~ **Closed** — see
  `apps/web/e2e/floors.spec.ts`. Every other spec that touches a
  building stopped at creating it on the `/buildings` list; this one
  is the first to actually open a building's detail page (reached via
  its generated `BLD-NNNNNN` reference, itself step 10) and use the
  floor form there. 34 Playwright specs green.
- **Checked the rest of spec §76's 50 steps against both the backend
  and the frontend while looking for the floors gap above, and found
  what looked like two genuinely missing features, not just missing
  tests** — worth recording precisely since "not yet done" so far in
  this file has mostly meant "exists but untested." One of the two
  turned out to be a research mistake, corrected in its own dedicated
  entry below (grepping only the backend for "drawing" missed that the
  frontend already offered it as a document type). The other, ~~step
  50, "Audit all significant changes"~~, **is a real closure.**
  `AuditEvent`/`record_audit_event`
  (`app/platform/audit.py`) had been writing a real, append-only trail
  since early in this build, but there was no way to read it back.
  Added: `GET /api/v1/audit` (`app/platform/router.py`), tenant-scoped
  via `get_tenant_db` the same way every other list endpoint is, with
  real limit/offset pagination (capped at 500, same shape as
  `list_repairs`) and server-side filtering by `entity_type`,
  `entity_id`, `action_code` and a `created_from`/`created_to` date
  range — this file's own load-testing entries are the reason it
  shipped paginated from the start rather than as an unbounded list.
  Gated by a new `platform.audit` permission, deliberately not granted
  to any role in `app/auth/rbac.py`'s `ROLE_PERMISSIONS` except via the
  OWNER/ADMIN wildcard — the same "permission string that exists only
  to be granted by the wildcard" convention as `billing.manage`/
  `org.manage_members`/`settings.write`, chosen because audit events
  can reveal any user's before/after values and IP address across
  every domain in the org, which is more sensitive than any one
  domain's own data. New Organisation → Audit log page
  (`apps/web/src/app/(app)/organisation/audit/page.tsx`) with the same
  filters plus a Previous/Next pager, and a "forbidden" state for
  non-admins matching the Users page's own pattern. Backend tests
  (`app/tests/test_audit.py`) cover tenant isolation, pagination, and
  the permission gate; `apps/web/e2e/audit-log.spec.ts` exercises the
  real flow end to end (add a property, then see it in the audit log).
- ~~Step 21, "Upload drawing metadata," had no `Drawing` model, no
  route, no UI~~ **That claim was wrong — corrected, and the one real
  gap it was hiding is now closed.** Re-grepping properly (the whole
  frontend too, not just the backend) found `"DRAWING"` already listed
  as a selectable `document_type` on the general `/data-and-uploads`
  upload form since early in the build, and on
  `ComponentDetailClient.tsx`'s own Evidence section. The generic
  `Document` model (`app/documents/models.py`) already tracks every
  field spec §28 names for drawing metadata specifically —
  `document_reference`, `title`, `document_type`, `revision`, `status`,
  `uploaded_by`/`uploaded_at`, `effective_date`,
  `superseded_by_document_id`, `related_entity_type`/`id`, `source`,
  `external_reference` — and "never silently overwrite previous
  versions" is handled the same append-only way `DocumentStatus.
  SUPERSEDED` already works for specifications. The one real gap:
  `DevelopmentDetailClient.tsx`'s own Evidence section (added earlier
  this session for O&M documentation) never offered `"DRAWING"` as an
  option — a one-line fix, `document_type` being a free-text column
  rather than a backend-enforced enum. Added
  `apps/web/e2e/drawing-metadata.spec.ts`: two tests proving a drawing
  uploaded against a component (the pre-existing path) and against a
  development (the newly-fixed path) both capture real metadata — a
  generated reference, the type genuinely recorded as `DRAWING`, and
  correct entity-linking cross-checked via the general documents list
  — not just that the upload succeeds. 42 Playwright specs green.
  ~~`api.uploadDocumentVersion`/`POST /documents/{id}/versions` (the
  "never overwrite, create a new revision instead" endpoint) exists
  and is already exercised by `app/tests/test_documents.py`, but no
  page anywhere has a "upload new version" button yet for *any*
  document type, drawings included~~ **Closed.** Added a "New version"
  action to both `ComponentDetailClient.tsx`'s and
  `DevelopmentDetailClient.tsx`'s Evidence sections: clicking it reveals
  an inline revision+file form scoped to that document row, and
  submitting calls the existing `api.uploadDocumentVersion`. Proven via
  `apps/web/e2e/document-new-version.spec.ts` (component-level and
  development-level) that the new version takes the previous one's
  place in the current-versions list — same title/type/reference,
  still exactly one `<li>` for it — rather than appearing as a second,
  duplicate-looking row, matching spec §28's "never silently overwrite"
  rule (the old row is marked `SUPERSEDED` on the backend, never edited
  in place; `GET /documents` already defaults to `current_only=true`).
  Caught two bugs while building this: first, adding a revision label
  to the document list's display text broke five pre-existing specs
  whose assertions matched the old `(TYPE)`-only text exactly — reverted
  the display change rather than updating five unrelated tests to
  match a cosmetic addition nothing asked for. Second, a latent race in
  the components "Add" form — the Type `<select>`'s default option is
  set by a `useEffect` once the list loads, and a test clicking "Add"
  before that default lands gets rejected with "Choose a component
  type first" even though the dropdown visually shows a selection —
  already worked around in `repeat-component-failure.spec.ts`/
  `component-warranty.spec.ts` but not in `drawing-metadata.spec.ts` or
  `commissioning-evidence.spec.ts`, which had been passing on luck;
  applied the same explicit-select-and-retry fix to both. 44 Playwright
  specs green, `npm run lint` clean.
- **The "upload new version" fix above only covered the two entity-
  scoped Evidence sections; the general, org-wide Documents table on
  `data-and-uploads/page.tsx` — the only other place any document
  (drawings, O&M manuals, specifications, certificates, anything
  uploaded from any page) shows up — had the identical gap.** Added the
  same "New version" button/inline revision+file form to that table's
  action column, reusing `api.uploadDocumentVersion` exactly as the
  other two do. `apps/web/e2e/document-new-version.spec.ts` gained a
  third test proving the same "replaces, not duplicates" behaviour
  there (a row-count check on the `<tr>`, same shape as the other two
  tests' `<li>` check). 45 Playwright specs green, `npm run lint`
  clean.
- **Spec §30 / architecture 03 §5's `building_control_records` table
  never existed at all — not a "backend built, frontend incomplete"
  gap like most of this file's other entries, a genuinely missing
  table.** `Building.building_control_reference`/`bsr_reference` (see
  building-control-reference.spec.ts) are bare `ExternalReference`
  strings captured at building/development creation — real, but only
  two fields. Spec §30 asks for the actual application lifecycle:
  Building Control body, application/approval dates, status,
  conditions, a separate completion reference, and supporting
  evidence — none of which existed anywhere. Added the real table,
  additive and untouched-existing-data: new migration
  `0032_building_control_records` (real RLS, same
  `_tenant_rls`/`_provenance_columns` pattern as every other table,
  verified against a real local Postgres — fresh-database
  `alembic upgrade head` all the way to head, downgrade, and the
  resulting schema/constraints/policy inspected directly via `psql`,
  not just assumed from the migration's own code), a new
  `ExternalReferenceType.BUILDING_CONTROL_COMPLETION_REFERENCE` member
  (application/BSR reuse the two existing reference types; only the
  completion reference needed a new one), `app/development/
  building_control_router.py` (`POST`/`GET`/`PATCH
  /api/v1/building-control-records`, gated by the existing
  `development.write` permission, no new permission needed), and
  `create_building_control_record`/`update_building_control_record`
  in `service.py`. "Completion certificate metadata" (spec §30) is
  deliberately not a separate field — the completion certificate is
  itself a Document, linked via the same `related_entity_type`/`id`
  evidence pattern every other section uses here
  ("building_control_record"), so its own metadata (title, reference,
  upload date) already is that. Added a "Building Control records"
  section to `BuildingDetailClient.tsx` (add/list/manage-status/
  evidence-upload, reusing the "New version"-style per-row toggle
  pattern) and `app/tests/test_building_control_records.py` (9 tests:
  creation against both a building and a development, missing-parent
  404, status transition with approval date and completion reference,
  invalid-status 400, list filtering, evidence linking, permission
  gate, tenant isolation). Deliberately NOT built: spec §31's full
  `regulatory_requirements`/`requirement_applicability` chain — a
  separate, much larger piece of work this table doesn't depend on and
  this entry doesn't claim to close. 46 Playwright specs green, 396
  backend tests green, `npm run lint` clean.
- **Checked Handover Readiness's own nine checks for the same
  "backend built, UI incomplete" shape as the Building Control
  reference gap above, and found two more: `check_warranties_received`
  and `check_om_documentation` (both `app/development/handover.py`)
  could never pass for any real development.** `check_warranties_
  received` has always queried `Warranty.component_id` — the model has
  supported a nullable `component_id` FK since `Warranty` was added —
  but the only "Add a warranty" form in the UI
  (`BuildingDetailClient.tsx`) only ever created building-scoped
  warranties, never component-scoped ones. `check_om_documentation`
  has always queried for a `Document` with
  `related_entity_type="development"` and a `document_type` containing
  "O&M" — `Document.related_entity_type`/`related_entity_id` has
  always supported linking to any entity, and
  `ComponentDetailClient.tsx`'s own "Evidence" section already proved
  that exact pattern for components (`construction-evidence.spec.ts`)
  — but `DevelopmentDetailClient.tsx` had no equivalent upload section
  at all. **Both closed.** Added a component-scoped "Add a warranty"
  form to `ComponentDetailClient.tsx`, reusing `api.createWarranty`
  exactly as the building form does, just passing `component_id`
  instead of `building_id`; added an "Evidence" section to
  `DevelopmentDetailClient.tsx`, modeled directly on
  `ComponentDetailClient.tsx`'s own, uploading with
  `related_entity_type="development"` against the development's own
  id (and now refreshing handover readiness alongside the document
  list on upload, so the score reflects it without a full page
  reload). `component-warranty.spec.ts` and
  `development-om-documentation.spec.ts` each prove the specific check
  genuinely flips from failing ("N component warranties missing" /
  "O&M documentation missing" in the development detail page's own
  readiness.missing list) to passing once the real UI action is taken
  — not just that the upload/add action itself succeeds. All 39
  Playwright specs green.
- ~~Handover Readiness' `COMMISSIONING_EVIDENCE` check
  (`check_commissioning_evidence`, spec §76 steps 34-35's "see missing
  information" / "resolve missing data") could never genuinely pass
  for any component any user actually created~~ **Closed** — the
  exact same "backend built, frontend incomplete" shape as the
  Building Control reference gap fixed earlier this session: the
  check has required a `Document` whose `document_type` contains
  "COMMISSIONING" since Post-Sprint-24, but the component evidence
  upload form's own type list never offered it. Added `"COMMISSIONING"`
  to `ComponentDetailClient.tsx`'s `DOCUMENT_TYPES` and a new spec,
  `apps/web/e2e/commissioning-evidence.spec.ts`, proving the check
  genuinely flips from failing to passing once such a document exists
  — not just that the upload succeeds. 35 Playwright specs green.
- ~~While building that fix, found two more checks in the same
  registry with the identical shape, still open~~ **Both also closed**
  — see the dedicated `check_warranties_received`/`check_om_
  documentation` entry above. Every one of Handover Readiness' 9
  checks is now genuinely satisfiable through the UI — a development
  can reach 100% readiness without an override purely by providing
  real data through the real UI, not just by the override-reason
  escape hatch `handover-authorisation.spec.ts` exercises.
- ~~Spec §77: "Upload compliance" had no Playwright spec~~ **Closed**
  — unlike the UI gaps just above, this one turned out to already be
  fully wired end to end: `COMPLIANCE_INSPECTIONS`
  (`app/operations/importers.py`'s `import_compliance_inspection_row`)
  is a real, registered importer, and `/data-and-uploads`'s dataset-
  type dropdown is populated straight from the backend's field
  dictionary rather than a hardcoded frontend list, so the dataset
  type was already selectable — it simply never had a spec exercising
  it, same shape as `operations-csv-import.spec.ts` (`REPAIRS`) and
  `commercial-csv-import.spec.ts` (`RENT_OBLIGATIONS`). Added
  `apps/web/e2e/compliance-csv-import.spec.ts`, mirroring both exactly:
  creates a compliance requirement and a building through the real UI,
  imports a CSV row referencing both by their generated codes, and
  confirms the resulting inspection shows up on the building's own
  detail page, not just the importer's own success count.
- ~~Spec §77: "Identify repeat repairs" had coverage for its sibling
  signal (`repeat-component-failure.spec.ts`, component-level) but
  none for the property-level one~~ **Closed** — added
  `apps/web/e2e/repeat-property-repairs.spec.ts`: three repairs against
  the same property with no component at all trigger
  `repeat_repairs_for_property`'s threshold-3-within-12-months signal
  on the repairs page, mirroring the component-level spec's exact
  structure for the sibling check. 37 Playwright specs green.

Specifically flagged as gaps to close early, not deferred to "later":

- **Data Health still doesn't cover all 15 items in spec §42.** Orphan
  components, duplicate components, missing handover information,
  missing serial numbers, missing/invalid installation dates,
  conflicting external references, and duplicate documents are all
  closed now (see the dedicated entries above) — still open: missing
  warranties, missing specifications, missing evidence, missing
  external references beyond UPRN, missing building relationships.
  Missing component types is not really open — `Component.
  component_type_id` is `NOT NULL` at the schema level, so no row can
  ever fail that check; there's nothing to query. Missing evidence
  needs real new tracking this codebase doesn't have yet (no document
  is linked to a specific compliance requirement in a way "missing
  evidence" could query). Missing warranties/specifications and missing
  building relationships were deliberately left as gaps rather than
  implemented as noisy blanket rules — see `rules.py`'s own module
  docstring for why (no per-component-type "this should have one" flag
  exists, and spec §19 explicitly says not to require every hierarchy
  level).
- **Dependabot PR #11 (grouped bump: eslint 9→10, eslint-config-next
  16.3.4→16.3.7, typescript 6.0.3→7.0.2) failed CI's "Web build & lint"
  job.** Investigated in an isolated worktree rather than assumed-fixable
  or ignored: `typescript` 7.0 breaks `typescript-eslint` (bundled
  transitively via `eslint-config-next`, which pins `typescript` to
  `>=4.8.4 <6.1.0` — TS 7.0 is a brand-new major the typescript-eslint
  ecosystem doesn't support yet), and independently, `eslint` 10 itself
  breaks `eslint-config-next`'s bundled `eslint-plugin-react` (a
  `context.getFilename` call that assumes ESLint 9's old `Linter` API).
  Both are real, confirmed upstream incompatibilities, not something
  worth papering over in this repo's own config. Isolated the actually-
  safe third of the group — `eslint-config-next` 16.3.4→16.3.7 alone —
  verified clean (`npm run build && npm run lint`, full `tsc --noEmit`,
  all 46 Playwright specs) in a worktree first, then applied directly to
  main rather than editing Dependabot's own branch. `eslint`/`typescript`
  deliberately left unbumped until their respective ecosystems support
  the new majors; Dependabot will re-propose them once a compatible
  `typescript-eslint`/`eslint-config-next` release exists.
- **While investigating the Dependabot PR above, `npm audit` surfaced 6
  real high-severity CVEs in the exact pinned `next` version
  (16.3.7)** — cache poisoning of SSG/ISR pages, information disclosure
  via the dev server's MCP endpoint and App Router metadata image
  routes, and Server-Side Request Forgery in Image Optimization among
  them (full list in the advisory links `npm audit` prints). A fix
  existed at `next@16.4.0` — a minor, non-breaking version per npm's own
  `isSemVerMajor: false` — so bumped straight to it rather than leaving
  known CVEs sitting in a pinned version. Verified clean the same way as
  the eslint-config-next fix (`npm run build && npm run lint`, `tsc
  --noEmit`, all 46 Playwright specs). `npm audit fix` (no `--force`)
  separately cleared `sharp`/`source-map-js`/`braces` as a side effect.
  5 high-severity findings remain, all transitively via `eslint-config-
  next`'s own outdated `micromatch`/`fast-glob` — dev-only lint tooling,
  never shipped to users, and `npm audit fix --force` would re-bump
  `eslint-config-next` into the same ESLint-10 incompatibility just
  diagnosed above, so left alone rather than forced.
- **CodeQL's code scanning tab had 4 open High-severity alerts, all from
  the "Analyze" CI jobs passing without being read.** Read each one
  rather than assuming pass-vs-fail CI status tells the whole story (a
  completed CodeQL job just means the scan ran, not that it found
  nothing). All 4 turned out to be real patterns CodeQL is right to flag
  in general, but each has a specific, checked reason it's not actually
  a vulnerability here: (1) `hash_session_token` (`app/core/tenancy.py`)
  flagged as weak password hashing — it hashes `new_session_token()`'s
  `secrets.token_urlsafe(32)` output, a 256-bit random value, never a
  user password (that path, `hash_password`, already uses bcrypt); a
  fast hash is the *correct* choice for an exact-match session-key
  lookup, not a weakness. (2-4) Three `print()` calls in
  `scripts/seed_demo.py` flagged as clear-text credential logging — they
  print `DEMO_PASSWORD`, a hardcoded, already-public constant
  (`"northstar-demo-2026"`, already commented "local/demo only" one line
  above its definition) specifically so whoever runs the fictional-
  demo-data seeder knows the login it just created; that's the feature,
  not a leak. First attempt used an inline `# lgtm[<rule-id>]` comment on
  each line, assuming it would suppress re-detection the way it did on
  the old lgtm.com service — wrong: GitHub's CodeQL Action doesn't honor
  that syntax, confirmed directly when the next push opened 4 brand-new
  alerts at the same (shifted) lines despite the comments. Fixed
  properly: dismissed each of the 4 new alerts via GitHub's own
  "Dismiss alert" UI with a `False positive` reason and a comment
  explaining why, which is the mechanism GitHub's CodeQL Action actually
  supports — confirmed by re-checking the code scanning tab afterward
  (0 open, 9 closed). Left the explanatory code comments in place (they
  document the reasoning regardless of whether they suppress anything)
  but removed the inert `# lgtm[...]` suffixes so a future reader isn't
  misled into thinking they do something. Full 396-test backend suite
  still green.



**With Docker** (once installed): `docker compose -f infra/docker-compose.yml up`,
then in another terminal: `cd apps/api && source .venv/bin/activate &&
python ../../scripts/seed_demo.py` (or run it inside the `api` container).
Web: http://localhost:3100. API: http://localhost:8000/docs.

**Real Postgres without Docker, without sudo** (how the RLS verification
above was actually done — this sandbox has no Docker and no admin
password available): Homebrew doesn't need `/opt/homebrew` or sudo —
`mkdir -p ~/homebrew && curl -L https://github.com/Homebrew/brew/tarball/main
| tar xz --strip-components 1 -C ~/homebrew` (use the `main` branch
tarball, not `master` — current Homebrew refuses to run from `master`
and `brew shellenv` prints an error instead of shell output if you
grab the wrong one), then `eval "$(~/homebrew/bin/brew shellenv)"` and
`brew install postgresql@16`. Starting the server needs
`LC_ALL="en_US.UTF-8"` set explicitly or `pg_ctl` fails with "postmaster
became multithreaded during startup" (a known macOS locale-detection
issue, not a real server fault) — `LC_ALL="en_US.UTF-8"
~/homebrew/opt/postgresql@16/bin/pg_ctl -D
~/homebrew/var/postgresql@16 -l <logfile> start`. Create a `datalume`
role/database matching `app/core/config.py`'s default
`DATABASE_URL` (adjust the port if not running on 5433), then
`DATABASE_URL=postgresql+psycopg://datalume:datalume@localhost:<port>/datalume
alembic upgrade head` runs the real migration chain. CI's `rls` job
does this same thing with an actual `postgres:` service container
instead, on every push — this local path is for a one-off manual check.

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
