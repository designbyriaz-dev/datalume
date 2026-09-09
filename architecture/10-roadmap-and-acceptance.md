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

Sprints 3–24 are not started; they are ordered and ready to pick up.

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
