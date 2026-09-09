# 09 — Threat Model, Testing Strategy, Observability, Deployment, Backup

Covers spec items 62, 74–75, 82–86.

## 1. Threat model (STRIDE-lite, tenant-SaaS-focused)

| Threat | Primary mitigation |
|---|---|
| Cross-tenant data access (IDOR) | Two-layer tenant scoping — app-layer `TenantScopedSession` + Postgres RLS (01 §1). Explicit security tests per spec §75. |
| Role escalation | Fixed, code-defined role→permission sets (01 §3); permission + tenant checks composed on every route. |
| Fabricated statutory data via AI | Structural: LLM has tool-call access only, no DB access, no write path to reference/status fields (03 §3, 06 §1). |
| Ambiguous payment misallocation | `NEEDS_REVIEW` status, no silent auto-allocation (05 §2). |
| Stolen session cookie | HttpOnly/Secure/SameSite cookie, short sliding TTL, server-side revocation via Redis (01 §2). |
| Malicious file upload | Upload goes to isolated object storage key first; worker validates structurally before any parse touches domain code; file type/size allow-list; virus scan hook reserved in pipeline (02 §2). |
| Secrets leakage in logs | Structured logger with a field allow-list; card/payment data and password hashes explicitly excluded from any log sink (spec §74/§62). |
| Webhook spoofing (Stripe) | Signature verification on every webhook before any billing state write (07 §2). |
| SSRF via document/URL fields | No server-side fetch of user-supplied URLs; document upload only, never "import from URL" in Build 1. |
| Unauthorised export of tenant data | Report/export endpoints require the same permission+entitlement checks as the underlying data, and are themselves audit events (07 §1). |

## 2. Testing strategy

**Unit** (spec §75): identifier generation & uniqueness (03 §3),
hierarchy traversal, component lifecycle scoring (03 §6), handover
readiness formula (03 §8), warranty date logic, defect calculations,
mapping/cleaning rules (02 §2/§6), Data Health rule registry (02 §5),
repeat repair/failure algorithms (04 §2), compliance status engine
(04 §4), rent/arrears calculations (05 §3), attention rule composition
(06 §3).

**Integration**: Development→Building→Property→Component chain;
Specification→Change (change control preserves history, 03 §7);
Component→Evidence; Development→Handover→Operational Property (identity
preserved, 03 §9); Component→Repair; Component→Planned Investment;
Property→Compliance; Rent→Payment→Arrears reconciliation end-to-end;
Ask→deterministic analytics (tool results match direct service calls).

**Security** (spec §75, mapped directly to the threat model above):
tenant isolation fuzz tests (attempt cross-org reads/writes for every
resource type via the standard test-client fixture, parametrised across
all `/api/v1/*` routers so a new module is covered automatically), IDOR
attempts against sequential/guessable IDs, role escalation attempts,
cross-org development/component/document/compliance/financial-data
access attempts, cross-org Ask DataLume grounding (a tool must not be
able to answer using another org's data even if asked to), cross-org
export attempts.

**E2E** (Playwright, already a project dependency): the acceptance tests
in spec §76–78 (New Build, Housing Operations, Commercial) are encoded
directly as Playwright scenarios — each of the 50 New Build acceptance
steps maps to an assertion in one continuous e2e flow, so "definition of
done" (spec §81) has an executable check, not just a checklist.

## 3. Observability

Structured JSON logging (`structlog`) with `organisation_id`,
`request_id`, `actor_user_id` on every log line. Error tracking via
Sentry (or equivalent) with PII scrubbing on the same field allow-list as
logging. Job monitoring: every `worker/jobs/*` run emits a
`job_run` record (status, duration, error) queryable by platform admins.
API monitoring: request duration/status histograms per route (OTel —
already partially wired per repo history in the sibling
`newhousingcomplianceapp` project; same pattern reused here via
`@vercel/otel` on the web app and `opentelemetry` Python SDK on the API).
Database monitoring: slow query log + connection pool saturation alerts.
AI monitoring: every Ask DataLume call logs tool calls made, token usage,
and whether the response was grounded — never logs the raw prompt/answer
text alongside PII beyond what's needed for debugging, retained on a
shorter cycle than general audit data. Billing monitoring: webhook
failure alerts (a missed Stripe webhook must not silently desync
entitlements). Audit monitoring: audit-write failures alert immediately
(an audit gap is itself an incident).

## 4. Deployment

Docker images for `api` and `web` (separate `Dockerfile.api` /
`Dockerfile.web`), `docker-compose.yml` for local dev (Postgres, Redis,
api, worker, web with hot reload). Target cloud: Azure, UK region
(spec §68) — Azure Container Apps or AKS for `api`/`worker`, Azure
Static Web Apps or a container for `web`, Azure Database for PostgreSQL
(Flexible Server), Azure Cache for Redis, Azure Blob Storage for
documents/evidence. Environment promotion: `local → staging → production`,
migrations (Alembic) run as a pre-deploy step, never on app boot in
production (avoids concurrent-migration races across multiple API
replicas).

## 5. Backup & recovery

Postgres: automated daily snapshots + point-in-time recovery (WAL
archiving), retention aligned to UK GDPR-oriented data retention policy
(configurable per data class — audit logs retained longest, session data
shortest). Object storage: versioning enabled on the documents/evidence
bucket (defence-in-depth alongside the application-level append-only
`documents` model in 02 §4 — belt and braces, since evidence/legal
records are the highest-consequence data class in this system). Backup
restore drills are a scheduled operational task, tracked outside this
architecture pack but referenced in the MVP backlog (10) as a Sprint 24
hardening item.
