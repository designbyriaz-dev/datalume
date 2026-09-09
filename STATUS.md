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

## Not yet done

Sprints 10–24 (construction evidence, change control, defects/
warranties, handover, Property 360, repairs, compliance, and the rest)
— not started. Full order and scope in
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
