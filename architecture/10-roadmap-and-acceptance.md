# 10 — MVP Backlog (24-Sprint Order) & Acceptance Matrix

## 1. Sprint plan (spec §80, expanded with what "done" means per sprint)

| # | Sprint | Key deliverables | Primary architecture refs |
|---|---|---|---|
| 1 | Foundation | Repo scaffold, docker-compose, Postgres+Alembic, auth (sessions, MFA-ready), organisations, workspaces, RBAC, tenant scoping (app + RLS), audit logging base, design tokens, marketing/auth screens, app shell (empty) | 00, 01, 07 §1, 08 |
| 2 | SaaS / Billing | Plans, subscriptions, Stripe adapter + checkout + portal + webhooks, entitlements enforcement | 07 §2–3 |
| 3 | Data Ingestion & Provenance | Datasets, import jobs, upload pipeline (validate/understand/map/review/import), provenance mixin adopted everywhere | 02 |
| 4 | Manual Entry / Documents / Evidence | "+Add" forms sharing import services, document versioning | 02 §3–4 |
| 5 | Property Model & Data Quality | Properties, spaces, Data Health rule registry v1 | 02 §5, 03 §1 |
| 6 | Development Hierarchy | Developments, buildings, floors, hierarchy queries | 03 §1 |
| 7 | Identifiers & Asset Coding | Reference generator, reference patterns, external reference model + hard write-path constraint | 03 §3 |
| 8 | Component Register | Components, taxonomy, parent/child, lifecycle fields | 03 §2 |
| 9 | Specifications / Documents / Golden Thread | Specification versioning, Golden Thread composed view | 03 §4 |
| 10 | Construction Evidence / Change Control | Evidence linking, change control with snapshot history | 03 §7 |
| 11 | Defects / Warranties | Defect & warranty registers, expiry alerts | 03 §8 |
| 12 | Handover & Operational Transition | Handover readiness engine, authorise workflow, status transition (no record duplication) | 03 §8–9 |
| 13 | Property 360 / Portfolio | Composed 360 view, portfolio rollups | 03 all, 06 §4 |
| 14 | Repairs / Component Failures | Repairs, repeat-repair & component-failure engines | 04 §1–2 |
| 15 | Compliance Foundation | Frameworks/domains/requirements/applicability, seeded 21 domains | 04 §3 |
| 16 | Compliance Operations / Safety / Hazards | Inspections, actions, hazards, damp & mould | 04 §5 |
| 17 | Compliance Assurance | Status engine, board assurance report | 04 §4/§6 |
| 18 | Stock Condition / Planned Investment | Surveys, planned investment scoring | 04 §6, 03 §6 |
| 19 | Tenancies / Commercial | Tenants, leases | 05 §1 |
| 20 | Rent / Payments / Arrears | Obligations, transactions, reconciliation, arrears/collection-rate | 05 §2–3 |
| 21 | Cross-Domain Attention Engine | Rule composition engine, nightly scan job | 06 §3 |
| 22 | Ask DataLume | Tool-use pipeline, grounded chat, explainability rendering | 06 §1–2 |
| 23 | Reporting | Report templates, PDF/XLSX/CSV export, background generation | 06 §4 |
| 24 | Security / Performance / Accessibility / Pilot Hardening | Full threat-model pass, security test suite, a11y audit, load testing, Northstar demo data complete, backup drill | 09 |

## 2. This handoff's status against the plan

**Architecture Pack: complete** (this directory).

**Sprint 1 (Foundation): scaffolded in this same session** — see
`../apps/` and `../infra/`. What's actually implemented vs. stubbed is
tracked in `../STATUS.md`, kept current as work continues; treat that
file, not this one, as the source of truth for "what exists today."
**Sprint 2 (SaaS / Billing): scaffolded, minus Stripe itself** — the
plan catalog, subscriptions, entitlements enforcement and billing
endpoints exist and are tested; `StripeBillingProvider` is deliberately
not implemented (no credentials in this environment) — see
`app/integrations/billing_provider.py` and STATUS.md.

**Sprint 3 (Data Ingestion & Provenance): scaffolded, minus the
background job queue** — the upload/validate/understand/map/review
pipeline, provenance mixin and dataset/import_job/import_row staging
model all exist and are tested (CSV only; XLSX deferred); IMPORT is a
registered-importer seam that's empty until Sprint 5+ domain tables
exist. See STATUS.md for the full list of what's simplified and why.

**Sprint 4 (Manual Entry / Documents / Evidence): Documents half
scaffolded** — append-only versioned Document storage (with a real
working local-disk adapter, not deferred) and its integration with
Sprint 3's ingestion pipeline are built and tested; "Manual Entry" as a
distinct feature needs a canonical domain entity to add and stays
conceptual until Sprint 5. See STATUS.md.

**Sprint 5 (Property Model & Data Quality): built** — Property/Space
(ProvenanceMixin's first real consumer), the shared create-entity
service manual entry and import both call, `IMPORTERS["PROPERTIES"]`
registered (closing Sprint 3's "honest no-op" for that dataset_type),
and a Data Health rule registry v1 (4 rules, unweighted-mean score,
fully transparent per-check breakdown). See STATUS.md for what's
simplified (reference generation, synchronous recompute) and why.

**Sprint 6 (Development Hierarchy): built** — Development/Building/Floor,
wired into Property/Space from Sprint 5 with every level except Property
staying optional; `resolve_property_hierarchy` derives and cross-checks
parent ids (a floor's building, a building's development) rather than
trusting the caller; the composed hierarchy-tree query
(`GET /developments/{id}/hierarchy`) satisfies the roadmap's "hierarchy
queries" item. No CSV import for this domain yet — manual entry only.
See STATUS.md.

**Sprint 7 (Identifiers & Asset Coding): built** — the real Reference
Engine (row-locked, org-configurable, same default output as the old
per-module generators it replaces) and the external reference model with
its hard write-path constraint enforced both in application code and via
a DB CHECK constraint. Every plain external-identifier column from
Sprints 5-6 (`Property.uprn`, `Development`/`Building`'s planning/
building-control/BSR reference columns) is now routed through
`app.identifiers.models.ExternalReference` instead, with the same public
API shape. See STATUS.md.

**Sprint 8 (Component Register): built** — `Component`/`ComponentType`
(spec §22), the latter reusing the global+org-specific seeded-catalog
pattern (system roles, Plans) with a non-standard RLS policy so the
global rows stay visible under tenant scoping. Components attach
independently to development/building/property/space/parent-component;
serial number routes through Sprint 7's `ExternalReference`; references
use Sprint 7's engine (`COMP-000001`). `IMPORTERS["COMPONENTS"]`
registered (closing Sprint 5's remaining "honest no-op" case), with
unmatched CSV type names auto-creating an org-specific custom type. See
STATUS.md for two real bugs the test suite caught (singular/plural type
matching, catalog-seeding order) and the live browser/curl verification.

**Sprint 9 (Specifications / Documents / Golden Thread): built** —
`Specification` (spec §27), attaching polymorphically to development/
building/property/space/component, with Document's exact append-only
versioning pattern (new row per revision, prior row marked SUPERSEDED,
never edited in place). Golden Thread (`GET
/api/v1/buildings/{id}/golden-thread`, spec §29) is a pure read-
composition over Specification/Component/Document/ExternalReference —
no new table — covering every link in the BUILDING → SPECIFICATION →
COMPONENT → RESPONSIBLE PARTY → EVIDENCE → APPROVAL chain that has a
canonical table today; inspection/change-control/handover are named
explicitly in the response as not yet available rather than omitted
silently, since those land in Sprints 16, 10 and 12. See STATUS.md for
the live browser/curl verification, including confirming a specification
revision resets approval rather than carrying it forward.

**Sprint 10 (Construction Evidence / Change Control): built** —
Construction Evidence (spec §32) reused Document's existing polymorphic
linking rather than a new table, per 03 §7. `ChangeControl` (spec §33)
is a real six-status workflow (submit → review → approve → implement,
plus reject/cancel) targeting a `specification_id`, with location copied
from it at submission rather than duplicated as four more nullable FKs
the way BUILD_PROMPT.md's "Conceptual fields" sketch shows — implementing
an approved change calls Sprint 9's own `create_specification_revision`,
so the append-only specification history stays the single source of
truth. Golden Thread's CHANGE link (§29) is now real. See STATUS.md for
the live-verification bug (a change control filtered by its
now-superseded specification id disappeared from the UI after
implementation — fixed by filtering on the stable related-entity
location instead) and the full browser/curl verification.

**Sprint 11 (Defects / Warranties): built** — `Defect` (spec §34) with a
real seven-state workflow and validated transitions, attaching like
Component rather than Specification's single polymorphic pair. `Warranty`
(spec §36) computes expiry status at read time instead of storing it, and
"configurable alerts before expiry" is a query parameter rather than a
fabricated notification channel this codebase has no infrastructure to
back. Defects Intelligence (spec §35) is a fixed set of aggregate reads,
not a scored engine — the spec's own examples are plain counts. See
STATUS.md for the full live browser/curl verification.

**Sprint 12 (Handover & Operational Transition): built** — the Handover
Readiness Engine (spec §37) is a nine-check weighted registry, per-org
configurable (spec's own emphasis on transparent/configurable scoring),
same shape as Data Health's rule registry but weighted from day one.
`HandoverService.authorise` (§9/§38) is exactly the transaction the
architecture specifies: assert readiness or a `development.handover`-
permitted override, flip in-scope `READY_FOR_HANDOVER` properties to
`HANDED_OVER` in one transaction, write a permanent per-property
`HandoverRecord` snapshot, audit each. Preserving development history at
handover (spec §39) needed no new code — it was already guaranteed by
every prior sprint's decision to key components/specifications/evidence/
warranties/defects to the same `properties` rows a status flip touches,
never a copy. See STATUS.md for the live verification and a real bug
the test suite caught (an empty development scoring ~85% instead of 0%,
since most checks vacuously pass when there's nothing to apply to yet).

**Sprint 13 (Property 360 / Portfolio): built** — Property 360 (spec
§41) composes property info, development/building/floor history,
components (with the same per-component specs/evidence/changes bundle
Golden Thread uses — extracted into a shared `composition.py` module
rather than duplicated), warranties, defects, handover record, Data
Health findings, and a Timeline sourced from `AuditEvent` rows every
sprint since 5 has been writing. Portfolio rollups give the Home
dashboard real backend-computed KPIs (properties/developments/
components, status breakdown, Data Health, defects, warranty expiry,
per-development handover readiness) in place of the ad-hoc client-side
fetch that had been there since Sprint 5. Also fixed a real gap found
while extending Golden Thread: its `not_yet_available` list still named
Sprint 12's handover as missing after Sprint 12 shipped — now a real
`handover_records` field. See STATUS.md for the full live verification.

**Sprint 14 (Repairs / Component Failures): built** — the first module
in a new `app.operations` domain package (architecture/04), gated by
the `operations.*` RBAC permissions carried since Sprint 1 but unused
until now. `Repair` requires `property_id` (a post-handover operational
concern, unlike Defect's fully-optional attachment). The Repeat Repair /
Component Failure engine (spec §44) is three deterministic,
independently testable functions with per-organisation configurable
thresholds (`RepairRuleConfig`, same lazy-seeded pattern as Sprint 7/12's
config tables) — "do not let the LLM invent calculations" enforced by
construction, not by prompting. Repairs Intelligence (spec §43) folds
those signals into the same fixed-aggregate-reads shape as Defects
Intelligence (Sprint 11). Property 360 now composes repairs for real,
closing the gap Sprint 13 had explicitly flagged. See STATUS.md for the
live verification, including confirming a rule-config change silences a
triggered signal immediately.

**Sprint 15 (Compliance Foundation): built** — the first four links in
spec §45-46's chain (FRAMEWORK → DOMAIN → REQUIREMENT → APPLICABILITY),
in a new `app/operations/compliance/` subpackage; inspections/actions
(Sprint 16) and the status engine (Sprint 17) are deliberately out of
scope. Reuses the global+org-specific catalog pattern from
`ComponentType` (Sprint 8) — `organisation_id` nullable, non-standard
RLS. Seeds only the 21 domain names (a stable taxonomy spec §45 names),
not requirement content, so as not to fabricate regulatory
interpretations (spec §31/§47). Requirement versions are grouped by
`(domain_id, code)` rather than a `lineage_id` column, append-only like
Specification (Sprint 9). First real use of the `operations.compliance`
RBAC permission. A duplicate-requirement-code gap was found during live
verification and fixed, with a regression test. See STATUS.md for the
full live verification narrative.

**Sprint 16 (Compliance Operations / Safety / Hazards): built** —
`Inspection`/`ComplianceAction` extend Sprint 15's compliance chain
(architecture §3); a new `app/operations/hazards/` subpackage
(architecture §5, spec §49) adds `Hazard`/`HazardAction` with damp &
mould modelled as a `hazard_type` value, not a parallel schema, plus a
repeat-hazard-occurrence engine reusing Sprint 14's pattern scoped by
`(property, hazard_type)`. `Hazard.status` is an enforced state machine
(REPORTED through CLOSED); `investigation_status` is a separate
outcome field. Also fixed a real gap found via live testing: Golden
Thread's `not_yet_available` list still claimed inspections had no
canonical table, which became false the moment this sprint built one —
now composed in for real, both building- and component-level. See
STATUS.md for the full live verification.

**Sprint 17 (Compliance Assurance): built** — `status_engine.py`
implements architecture §4's `compliance_status` pseudocode close to
line-for-line (all ten statuses), computed fresh on every read from
Inspection/ComplianceAction/RequirementApplicability, nothing
persisted (spec §47: never LLM-set, no write path into a status
column because there is no status column). Two signals the pseudocode
names without defining (`UNKNOWN` vs `MISSING_EVIDENCE`, and
`requires_review`) are resolved with documented, config-driven
readings rather than guessed. `assurance.py` is the Board Assurance
report (spec item 57) — a read-only rollup over already-computed
status, gated by the existing `reports.board` permission's first real
use. See STATUS.md for the full live verification, including the
Building detail page's status badge updating live after an inspection.

**Sprint 18 (Stock Condition / Planned Investment): built** —
`StockConditionSurvey` (architecture §6) feeds two new Data Health
checks (missing/stale surveys). `planned_investment.py` implements
architecture §6's `investment_priority` scoring pseudocode: five
weighted, independently-explainable factors (spec §40: "do not use age
alone"), computed at read time rather than via the pseudocode's
nightly-job framing — this build has no job/worker infrastructure
until Sprint 21 introduces one, so this follows every other scoring
engine already built (Data Health, Handover Readiness, repeat-repair/
hazard, Sprint 17's compliance_status) instead of building a job
runner two sprints early. A documented RBAC fix gives ASSET_MANAGER
`operations.write`, which it needs to actually record the surveys this
sprint is about. See STATUS.md for the full live verification,
including a hand-checked score against the weighted-average math.

**Sprint 19 (Tenancies / Commercial): built** — a new `app.commercial`
top-level package (mirroring `app.development`/`app.operations`) adds
architecture §1's `Tenant`/`Lease` tables only; `rent_obligations`/
`payment_transactions`/`payment_allocations` and reconciliation/
arrears are Sprint 20's own split, not this sprint's. `lease_status` is
an enforced workflow; `occupancy_status` is deliberately not, since it
isn't directional. First real use of the `commercial.read`/
`commercial.write` RBAC permissions carried since Sprint 1. Also closed
Property 360's stale "tenancy_and_lease" not-yet-available entry (now
composed for real) and reworded two other entries found stale in
passing (compliance/stock-condition tables exist but aren't composed
into Property 360 yet — flagged as separate follow-up work, not
folded into this sprint). See STATUS.md for the full live verification.

**Sprint 20 (Rent / Payments / Arrears): built** — completes
architecture §1's schema (RentObligation, PaymentTransaction,
PaymentAllocation, kept as three tables joined only through
allocations, never a combined ledger row). `reconciliation.py`
implements spec §52's four ordered matching rules exactly, with
NEEDS_REVIEW whenever a rule finds more than one equally-plausible
candidate — "never silently allocate ambiguous money" enforced by the
algorithm's shape. `arrears.py` implements §3's arrears/collection-rate
pseudocode, pure and computed at read time. One documented deviation
from this codebase's usual "always computed, never one-time" norm:
reconciliation runs once per payment, not re-evaluated retroactively,
matching how real reconciliation works. First real use of the
commercial.payments RBAC permission (RENT_MANAGER-only). See STATUS.md
for the full live verification, including a config-driven due-date-
window test in the same style as every other engine sprint.

**Sprint 21 (Cross-Domain Attention Engine): built** — this codebase's
first genuine scheduled background job: app/worker/main.py (idle since
Sprint 1) now runs a nightly attention scan for every organisation, no
new scheduling dependency. Four rules, matching architecture's own four
named examples, each a join + threshold over an already-built engine
(Warranty+Defect, Sprint 14's repeat-repair signals, Sprint 17's
compliance_status, Sprint 20's arrears) — never restating another
domain's logic. AttentionRule is always org-scoped (a documented
deviation from the SQL sketch's NULL-catalog allowance, since there's
no rule-authoring DSL for a shared catalog to serve). Two real bugs
caught during this sprint's own test-writing: the upsert logic didn't
actually respect a dismissed signal, and the rules list endpoint was
missing the commit every other lazy-seeding endpoint has, both fixed
and regression-tested. See STATUS.md for the full live verification,
including the Home dashboard's new live-updating "Needs attention"
section.

**Sprint 22 (Ask DataLume): built** — implements architecture §1's full
pipeline boundary (DATA → ... → DETERMINISTIC ANALYTICS → CONTROLLED AI
TOOLS → LLM INTERPRETATION → USER): seven typed tools in
`intelligence/ask/tools.py`, each a thin wrapper over an already-built
deterministic engine (Sprints 11/13/14/17/18/20) — the LLM never gets
database access, only typed `ToolResultOut` rows. Tool selection is
deterministic application code (keyword + entity-type matching), never
delegated to the LLM's own judgement, a deliberate strengthening of
spec §57's "never invent" guarantee beyond native function-calling.
`grounded=False` is enforced structurally in the API layer before any
LLM call — the fixed "I don't have data" response is not a prompt
request, it's the code path taken when no tool matches. LLM
interpretation follows Sprint 2's BillingProvider adapter precedent
(`LLMProvider` Protocol, `NullLLMProvider`, `AnthropicLLMProvider`),
using the Python `anthropic` package rather than the architecture doc's
literal `@anthropic-ai/sdk`, since every other domain in this codebase
lives in the FastAPI backend and introducing a second server-side
runtime for one package name would break that pattern for no benefit.
No `ANTHROPIC_API_KEY` is configured in this environment, so all
testing exercises `NullLLMProvider`'s templated-summary fallback,
proving the grounding pipeline works fully independently of whether an
LLM is configured — exactly the property spec §57 requires. See
STATUS.md for the full live verification, including a grounded
compliance question with its expandable explainability panel and an
explicitly ungrounded fallback question.

**Sprint 23 (Reporting): built** — implements architecture §4's "a
report is a rendering target, not a separate data path": all five
named report types (Development Summary, Handover Readiness,
Compliance Executive Summary, Board Assurance, Commercial Portfolio)
are composed entirely from already-built service-layer functions into
one generic content shape, rendered to PDF (ReportLab)/XLSX
(openpyxl)/CSV. Report generation runs on Sprint 21's now-real worker
loop rather than repeating Sprint 3's synchronous ImportJob workaround
— architecture explicitly requires background generation, and the
infrastructure to do it for real now exists. The two board-level
report types reuse the existing `reports.board` permission the
`/assurance-report` endpoint already enforces, checked at both request
and download time, so exporting isn't a permission side door. A real
bug — a foreign key the worker process never resolved because nothing
in its own imports pulled in the `users` table — was caught only by
running the worker as a genuinely separate process during this
sprint's live verification, not by the pytest suite (which always
builds its FastAPI client through `app.main`, masking the gap). See
STATUS.md for the full live verification, including watching a report
job go PENDING → READY with no manual refresh.

**Sprint 24 (Security / Performance / Accessibility / Pilot Hardening):
built, honestly scoped** — this sandbox has no Postgres, no real Redis,
no cloud target and no load-generation infra, so §09's full scope
("threat model, security tests, a11y audit, load testing, demo data,
backup drill") was triaged into what's genuinely buildable and
verifiable here, documented rather than checkbox-claimed. Built: a
systematic tenant-isolation fuzz suite covering all 15 GET-by-id
resource types across every domain (spec §75's own wording) — no leak
found, application-layer isolation confirmed for the first time (RLS
itself still isn't, no Postgres to run it against); real structured
JSON logging (organisation_id/request_id/actor_user_id bound via
structlog contextvars, so every log line during a request carries them
automatically, not just one summary line); Northstar demo data for
both named orgs (Housing and Commercial), seeded through the real API
via TestClient rather than hand-built rows, verified idempotent by
running it twice. Three real bugs found and fixed, not just documented:
a missing audit event on report export (architecture's own threat
table names this explicitly), a Redis outage in the new logging
middleware taking down entire requests instead of degrading (caught by
this sprint's own concurrency smoke-check — every request failed until
fixed), and an unbounded file-upload size across three endpoints (a
real DoS gap). One real accessibility bug fixed (sign-in/sign-up's
label-input association); the same pattern across 17 more pages is
flagged as a follow-up task rather than fixed here. See STATUS.md for
the full breakdown, including what's explicitly out of scope and why
(real load testing, a real backup drill, full OTel/Sentry span tracing,
the Playwright E2E acceptance suite).

All 24 roadmap sprints are now built.

## 3. Acceptance matrix (spec §76–78, condensed to trace-to-architecture)

| Acceptance area | Spec ref | Satisfied by |
|---|---|---|
| Sign in, create org, RBAC-gated navigation | §76.1-2 | 01 §2–5 |
| Create development, generate internal reference, enter external references (planning/BC/BSR) without fabrication | §76.3-8 | 03 §1, §3 |
| Add building, floors, planned properties + references | §76.9-13 | 03 §1, §3 |
| Add components + references, manufacturer/model/serial/install date/warranty | §76.14-19 | 03 §2 |
| Upload specification/drawing/construction evidence linked to exact component | §76.20-23 | 02 §4, 03 §4/§7 |
| Record inspection, propose change preserving previous spec, approve/reject | §76.24-27 | 03 §7 |
| Record/assign/complete defect, upload completion evidence | §76.28-31 | 03 §8 |
| Monitor warranty | §76.32 | 03 §8 |
| View handover readiness, missing info, resolve, authorise, convert to operational preserving identity/components/evidence/history | §76.33-41 | 03 §8–9 |
| Open operational Property 360 showing new-build history | §76.42-43 | 03 §1/§9, 06 §4 |
| Add repair linked to component, view lifecycle & planned replacement | §76.44-47 | 03 §6, 04 §1 |
| Ask questions, generate handover report, audit all changes | §76.48-50 | 06 §1–2, 06 §4, 07 §1 |
| Upload/manually add operational data, Data Health, 21-domain compliance, inspections/evidence/actions, hazards, damp & mould | §77 | 02 §5, 04 §3/§5 |
| Property 360, repeat repairs, component failures, Attention Engine, grounded Ask, management/board reports | §77 | 03 §1, 04 §2, 06 §3–4 |
| Properties/units/tenants/leases, rent import, payment import/reconciliation, arrears, collection rate, lease events, Property 360, grounded Ask, reports | §78 | 05, 06 §1–2/§4 |

## 4. What "done" means (spec §81, restated as an architecture-level gate)

No sprint above is considered complete until each of its features has:
frontend + backend + database + auth + authorisation + tenant isolation
+ validation + provenance + audit + error handling + tests + real data
flow (no mocked production path) + loading states + empty states +
documentation. This is enforced practically by the shared
create/update/delete service mixins (provenance + audit built in, 07 §1)
and the shared route-protection decorator (tenant + permission +
entitlement, 07 §4) — a feature that skips one of these has to actively
opt out of the shared machinery, which is the review signal that it is
not actually done.
