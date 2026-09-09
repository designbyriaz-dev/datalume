# 01 — Platform Foundations: Multi-tenancy, Auth, RBAC, Organisations, Workspaces

## 1. Multi-tenancy model

**Decision:** row-level multi-tenancy. Every tenant-scoped table carries a
non-nullable `organisation_id`, and every query goes through a
`TenantScopedSession` that automatically injects `WHERE organisation_id =
:current_org` — never left to individual endpoint authors to remember.

Enforcement is layered, in order of "cheapest to bypass by accident" to
"hardest to bypass":

1. **Application layer:** a FastAPI dependency (`get_tenant_db`) resolves
   `organisation_id` from the authenticated session and returns a
   query-helper bound to it. Domain services accept this helper, not a
   raw `Session`, so it is a type error to query without tenant scope.
2. **Postgres Row Level Security (RLS):** every tenant table has an RLS
   policy on `organisation_id = current_setting('app.current_org_id')`.
   The API sets this session variable at the start of every
   request-scoped transaction. This is the safety net for the case where
   application-layer scoping is forgotten or a raw query slips through.
3. **Audit:** every read of cross-tenant platform-admin data (support
   tooling) is itself audited and requires an elevated `PLATFORM_ADMIN`
   role distinct from any organisation role.

**Rationale:** RLS alone is not enough (easy to forget `SET
app.current_org_id`, easy to get wrong in migrations/scripts);
application-layer scoping alone is not enough (one missed `.filter()` is
an IDOR). Two independent layers catching the same class of bug is the
standard defence-in-depth answer to "never rely on frontend filtering
alone," which the spec calls out explicitly.
**Alternatives:** schema-per-tenant (rejected — see 00, migration/ops
cost at scale); database-per-tenant (rejected for Build 1 — enterprise
option for later, revisit if a contract requires it).
**Future impact:** the `TenantScopedSession` abstraction is also the seam
where a future "move this tenant to its own database" migration would
plug in — swap the connection, not the query code.

## 2. Authentication

- Session-based auth (HttpOnly, Secure, SameSite=Lax cookie) rather than
  client-stored JWT, to avoid XSS-exfiltrable tokens in a browser app.
  Sessions are opaque IDs stored in Redis with a short sliding TTL,
  refreshed on activity.
- Passwords: `bcrypt` via `passlib`, minimum policy enforced server-side.
- MFA: TOTP (RFC 6238) as an optional-then-mandatory-for-admins control;
  architecture reserves a `mfa_methods` table so SMS/WebAuthn can be
  added without a schema rewrite.
- Service-to-service and future public API access uses separate scoped
  API keys (`platform.api_keys`), never end-user sessions.
- Every login, failed login, password reset, MFA change and session
  revocation is an audit event.

**Decision:** cookie session over JWT for the browser app.
**Rationale:** JWTs in `localStorage` are XSS-exfiltrable; JWTs in
cookies still need CSRF handling and gain little over an opaque session
for a server-rendered/first-party SPA. Redis-backed sessions can be
revoked instantly (needed for "sign out everywhere," offboarding,
security incidents) — a stateless JWT cannot be revoked without an
allow/deny-list, which reintroduces the state you were trying to avoid.
**Trade-off:** requires Redis to be available for every authenticated
request (already a Build 1 dependency for jobs/cache, so no new
infrastructure).

## 3. RBAC

Two-tier permission model:

```
ROLE (per organisation membership) → PERMISSIONS (fixed capability set)
```

Initial roles (from spec §63): `OWNER`, `ADMIN`, `DATA_ANALYST`,
`MANAGER`, `VIEWER`, plus the domain-specific roles the spec lists as
architecture must support: `DEVELOPMENT_MANAGER`, `HANDOVER_MANAGER`,
`ASSET_MANAGER`, `REPAIRS_MANAGER`, `COMPLIANCE_MANAGER`,
`BUILDING_SAFETY_MANAGER`, `PROPERTY_MANAGER`,
`COMMERCIAL_PROPERTY_MANAGER`, `LEASE_MANAGER`, `RENT_MANAGER`,
`FINANCE_VIEWER`, `EXECUTIVE`.

```sql
roles(id, code, name, is_system_role, organisation_id NULL for system roles)
permissions(id, code)               -- e.g. "development.write", "compliance.approve"
role_permissions(role_id, permission_id)
memberships(id, user_id, organisation_id, role_id, workspace_id NULL, status, invited_by, created_at)
```

**Decision:** roles carry a fixed, versioned permission set defined in
code (not end-user-editable in Build 1), but the *assignment* of roles to
users per organisation/workspace is fully dynamic.
**Rationale:** the spec's acceptance tests and domain list imply ~17
roles with materially different capability sets; letting every tenant
define arbitrary custom permission bundles in Build 1 would explode QA
surface for limited value. Fixed role→permission mapping in code, seeded
into `role_permissions`, keeps the security model auditable while still
letting admins assign the right role per person per org/workspace.
**Future impact:** custom roles are a natural Build 2 feature — the
schema already supports `organisation_id` on `roles` for a
tenant-defined role, so it is additive, not a migration.

Permission checks are a FastAPI dependency:
`require_permission("development.write")`, resolved against the caller's
membership for the `organisation_id` embedded in the route/tenant
context — so a permission check and a tenant-scope check happen in the
same place, closing the classic "authorised in general, but for the
wrong org" IDOR class explicitly called out in spec §75 security tests.

## 4. Organisation model

```sql
organisations(
  id, name, slug, organisation_type,     -- HOUSING_ASSOCIATION | LOCAL_AUTHORITY |
                                          -- MANAGING_AGENT | PRIVATE_LANDLORD |
                                          -- COMMERCIAL_LANDLORD | BUILD_TO_RENT |
                                          -- PROPERTY_MANAGEMENT_CO | SUPPORTED_HOUSING |
                                          -- PROPERTY_INVESTOR | OTHER
  goals JSONB,                           -- selections from onboarding §8
  status,                                -- TRIAL | ACTIVE | SUSPENDED | CANCELLED
  region, timezone,
  created_at, updated_at
)
organisation_config(
  organisation_id, key, value JSONB      -- adaptive nav/KPI/terminology config (see §5)
)
```

Onboarding (spec §8) writes `organisation_type` and `goals`, which the
**Adaptive Workspace Engine** (below) reads to compute navigation, KPI
selection, terminology and default Attention Engine rules — configured,
never hard-coded per sector, satisfying "one core, adaptive
configuration."

## 5. Workspace engine

A `workspace` is a scoping unit inside an organisation (e.g. a Housing
Association may run a "Development" workspace and an "Operations"
workspace with different default navigation/KPIs, while a small landlord
has exactly one workspace). Most Build 1 tenants will have a single
default workspace created automatically at signup; multi-workspace is
there for larger tenants without being a mandatory concept smaller ones
ever see.

```sql
workspaces(id, organisation_id, name, workspace_type, config JSONB, created_at)
```

`AdaptiveWorkspaceResolver` (a pure function in `organisations/adaptive.py`)
takes `(organisation_type, goals, workspace_type)` and returns:

```python
class WorkspaceLayout(BaseModel):
    nav_sections: list[NavSection]
    home_kpis: list[KpiKey]
    terminology: dict[str, str]          # e.g. {"property": "unit"} for commercial
    compliance_domains: list[str]        # subset of the 21 domains that apply
    default_attention_rules: list[str]
```

This single function is unit-tested directly (spec §75) against every
organisation type in §10/§11, so "Housing Association sees Development
prominently, Commercial Landlord sees Leases prominently" is a data-driven
config lookup, not per-page conditional rendering sprinkled through the
frontend.
