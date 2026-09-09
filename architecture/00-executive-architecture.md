# 00 — Executive Architecture

## 1. What Build 1 is

A single multi-tenant modular monolith that ingests, cleans, connects and
explains property information across the full lifecycle — development
through operations through disposal — for organisations ranging from a
50-property landlord to a 50,000+ property enterprise provider.

One core. One web platform. One property data model. One intelligence
engine. Adaptive configuration per organisation type, never a forked
product.

## 2. System diagram

```
                              ┌─────────────────────────┐
                              │   Next.js Web Platform   │
                              │  (apps/web) — TS/React   │
                              │  light app shell +       │
                              │  dark marketing/auth     │
                              └────────────┬─────────────┘
                                           │ HTTPS / JSON
                                           │ (session cookie, CSRF)
                              ┌────────────▼─────────────┐
                              │   FastAPI Core (apps/api) │
                              │  modular monolith:        │
                              │  auth · orgs · workspaces  │
                              │  development · assets      │
                              │  operations · commercial   │
                              │  intelligence · platform    │
                              └───┬─────────┬─────────┬────┘
                                  │         │         │
                     ┌────────────▼──┐ ┌────▼─────┐ ┌─▼──────────────┐
                     │  PostgreSQL   │ │  Redis   │ │ Object Storage  │
                     │  (per-tenant  │ │ (jobs,   │ │ (uploads,       │
                     │  row scoped)  │ │ cache,   │ │ evidence,       │
                     │               │ │ sessions)│ │ documents)      │
                     └───────────────┘ └────┬─────┘ └─────────────────┘
                                             │
                                   ┌─────────▼──────────┐
                                   │  Background Worker   │
                                   │  (RQ/Arq on Redis)   │
                                   │  ingestion, mapping,  │
                                   │  cleaning, analytics,  │
                                   │  alerts, reports       │
                                   └─────────────────────┘
```

External integrations (Stripe for billing, email provider, future
Housing Management System connectors) sit behind adapter interfaces in
`apps/api/app/integrations/` — never called directly from domain code.

## 3. Repository structure

```
datalume/
  architecture/            ← this Architecture Pack
  docs/                    ← original handoff spec (BUILD_PROMPT, DESIGN_SYSTEM)
  apps/
    web/                   ← Next.js 15 (App Router), TypeScript, Tailwind
      src/
        app/               ← routes: (marketing)/, (auth)/, (app)/
        components/        ← design-system components (Card, KpiStat, Badge…)
        lib/                ← api client, auth helpers, org context
        styles/
    api/                   ← FastAPI, Python 3.11+, SQLAlchemy 2.x, Alembic
      app/
        core/              ← config, security, db session, tenancy middleware
        auth/               ← authentication, sessions, RBAC
        organisations/       ← org, workspace, membership
        development/          ← development, building, hierarchy, components,
                                identifiers, specifications, golden thread,
                                evidence, change control, defects, warranties,
                                handover
        operations/            ← repairs, compliance, hazards, damp & mould,
                                stock condition, planned investment
        commercial/              ← tenancies, leases, rent, payments, arrears
        intelligence/             ← attention engine, ask, reporting, analytics
        platform/                  ← audit, subscriptions, billing, entitlements
        integrations/               ← stripe.py, storage.py, email.py (adapters)
        worker/                     ← background job definitions
        tests/
      alembic/
  infra/
    docker-compose.yml     ← postgres, redis, api, worker, web (local dev)
    Dockerfile.api
    Dockerfile.web
  scripts/
    seed_demo.py           ← Northstar Housing / Northstar Commercial seed data
```

**Decision:** monorepo, two apps (`web`, `api`), one shared Postgres schema
with `organisation_id` on every tenant-scoped table.
**Rationale:** Build 1 explicitly avoids microservices; a monorepo keeps
API contracts and types easy to keep in sync at this stage, and a single
schema with row-level tenancy is the simplest correct way to guarantee
"never rely on frontend filtering alone."
**Alternatives considered:** schema-per-tenant Postgres, separate services
per domain.
**Trade-off:** schema-per-tenant gives stronger physical isolation but
makes cross-tenant platform admin, migrations and connection pooling much
harder at this stage; row-level tenancy is proven at the target scale
(largest tenant ~50k properties) when paired with mandatory tenant-scoped
query helpers and DB-level Row Level Security as a second enforcement
layer.
**Future impact:** if a single enterprise tenant later needs contractual
physical isolation, that tenant can be moved to a dedicated database
without changing the domain code, because every query already goes
through the same tenant-scoping layer.

## 4. Module boundaries

Each Python package under `apps/api/app/` owns its own SQLAlchemy models,
Pydantic schemas, service functions and FastAPI router. Cross-module
reads go through service functions, never direct ORM queries into another
module's tables — this is what lets Build 1 stay a modular monolith that
could be split into services later without a rewrite.

| Module | Owns | Depends on |
|---|---|---|
| `core` | config, db session, tenancy context, security primitives | — |
| `auth` | users, sessions, MFA, RBAC | `core`, `organisations` |
| `organisations` | organisations, workspaces, membership, org config | `core` |
| `development` | developments → components, golden thread, handover | `core`, `organisations`, `platform` (documents) |
| `operations` | repairs, compliance, hazards, stock condition | `core`, `organisations`, `development` (components) |
| `commercial` | tenancies, leases, rent, payments, arrears | `core`, `organisations` |
| `intelligence` | attention engine, Ask DataLume, reporting, analytics | reads across all domain modules via service functions |
| `platform` | audit, subscriptions, billing, entitlements, documents | `core`, `organisations` |
| `integrations` | Stripe, object storage, email | called by `platform`, `development` |
| `worker` | async ingestion, mapping, cleaning, alerts, report generation | all modules |

## 5. Why a modular monolith, not microservices for Build 1

Build 1's own instruction is explicit: avoid unnecessary microservices.
The domains above (development, operations, commercial, intelligence) are
deeply cross-referential (a repair links to a component links to a
warranty links to a compliance action) — splitting them into services
before the data model has stabilised would mean distributed transactions
and eventual consistency for what should be simple joins. The module
boundaries above are drawn so that a future split (most likely candidate:
`intelligence` as its own service once Ask DataLume needs independent
scaling) is a matter of extracting a package, not re-architecting.
