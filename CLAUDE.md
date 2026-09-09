# DataLume Property Intelligence — Build Instructions

You are building **DataLume**, a multi-tenant B2B Property Intelligence SaaS
platform for UK housing associations, local authorities, managing agents,
commercial landlords, and property developers.

## Read first

1. `docs/BUILD_PROMPT.md` — the full, authoritative product & technical
   specification. This is the source of truth for every model, module,
   workflow, and constraint. Read it in full before writing any code.
2. `docs/DESIGN_SYSTEM.md` — the visual design system, derived from approved
   UI mockups (dashboard + landing/sign-in). Match this styling exactly for
   any UI work.

## The single most important rule

**Do NOT generate the full application yet.**

Your first deliverable is the **DataLume Build 1 Architecture Pack**
(spec section 79 in `BUILD_PROMPT.md` lists everything it must contain:
executive architecture, system diagram, repo structure, module boundaries,
ER model, multi-tenancy, RBAC, every domain model, API spec, screen map,
design system, threat model, testing strategy, MVP backlog, acceptance
matrix — 88 items in total).

Produce that Architecture Pack as a set of markdown documents (e.g. under
`architecture/`), present it, and **stop and wait for explicit approval**
before writing any implementation code. Do not create disconnected mock
screens and present them as a finished product. Do not use production-
critical mocked functionality anywhere.

## Non-negotiable constraints (see BUILD_PROMPT.md for full detail)

- **One platform, not several products**: one DataLume Core, one web
  platform, one shared property data model, one shared intelligence engine,
  with adaptive configuration per organisation type. Never fork into
  separate apps per sector.
- **Never fabricate official identifiers or statutory data**: UPRNs,
  Building Control references, BSR references, planning references,
  compliance status, defect counts, warranty dates, rent/arrears figures —
  all of these must come from real data, never be invented by an LLM.
  DataLume generates *internal* references only, clearly distinguished from
  *external/official* ones.
- **Deterministic analytics, LLM explains — never calculates**: repeat-repair
  detection, compliance status, arrears ageing, handover readiness scoring,
  etc. must be deterministic, versioned, and auditable. The AI layer
  ("Ask DataLume") sits on top of controlled tools and explains results; it
  never invents figures.
- **Strict tenant isolation** enforced at the server/data layer on every
  query — never rely on frontend filtering alone.
- **Full data provenance** on every important record (source type/system,
  import job, created/updated by & when).
- **Preferred stack**: Next.js/React/TypeScript frontend, Python/FastAPI
  backend, PostgreSQL, Polars/Pandas for data work, Redis + a job worker for
  background processing, secure cloud object storage, Azure/UK-region
  preferred, modular monolith (avoid microservices for Build 1).
- **Definition of done** for any feature = frontend + backend + database +
  auth + authorization + tenant isolation + validation + provenance + audit
  + error handling + tests + real data flow + loading/empty states +
  documentation. A feature is not done just because a screen exists.

## Suggested working order after the Architecture Pack is approved

Follow the 24-sprint implementation order in section 80 of
`BUILD_PROMPT.md`, starting with Foundation → SaaS/Billing → Data
Ingestion & Provenance, and working through Development, Components,
Golden Thread, Handover, Property 360, Repairs, Compliance, Commercial,
the Attention Engine, Ask DataLume, Reporting, and finally hardening.

## Demo data

Build the fictional demo org **Northstar Housing** (~12,480 operational
properties) and the fictional new development **Riverside Gardens**
(84 homes) as described in `BUILD_PROMPT.md` sections 70–71. Label all demo
data as clearly fictional/synthetic.
