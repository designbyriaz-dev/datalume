# 07 — Platform Services: Audit, Subscriptions, Billing, Entitlements, API

Covers spec items 61, 64–65, 69 (SaaS commercial model, billing, audit,
API specification).

## 1. Audit

```sql
audit_events(id, organisation_id, actor_user_id NULL, action_code,
             entity_type, entity_id NULL, before JSONB NULL,
             after JSONB NULL, ip_address, user_agent, created_at)
```

Written via a single `AuditLogger.record(...)` call embedded in the base
service-layer write helpers (create/update/delete mixins) rather than
scattered per-endpoint — so the spec §61 list (logins, uploads, manual
records, edits, development/property/component creation, identifier
generation, specification changes, document versions, change control,
defects, warranties, handover, compliance changes, payment allocations,
reports, exports, permissions, Ask activity, subscription changes) is
covered by construction: anything that goes through the shared
create/update/delete path is audited automatically, and the checklist
above is the acceptance test for "did we forget a module," not a
per-feature manual task. Append-only table, no update/delete path
exposed even to admins — corrections are new events, never edits to
history.

## 2. Subscriptions & billing

```sql
plans(id, code, name, price_monthly, price_annual, property_count_tier_min,
      property_count_tier_max NULL, entitlements JSONB)
subscriptions(id, organisation_id, plan_id, status,
              -- TRIALING | ACTIVE | PAST_DUE | CANCELLED
              current_period_end, stripe_subscription_id,
              stripe_customer_id, created_at, updated_at)
usage_records(id, organisation_id, metric, value, period_start, period_end)
```

`ORGANISATION → SUBSCRIPTION → PLAN → ENTITLEMENTS → USAGE → BILLING`
(spec §64) maps directly: `entitlements` on `plans` is the source of
truth for feature/limit gating (`require_entitlement("component_register")`
FastAPI dependency, same shape as `require_permission`), `usage_records`
feeds property-count-tier billing and any future usage-based add-ons.

**Decision:** Stripe behind an `integrations/stripe.py` adapter
implementing a small internal `BillingProvider` protocol
(`create_checkout_session`, `create_billing_portal_session`,
`handle_webhook_event`), never called directly from `platform/` service
code.
**Rationale:** spec §65 says "Stripe or equivalent abstraction" —
Build 1 uses Stripe concretely but the adapter boundary means swapping
or adding a provider (e.g. an enterprise contract billed manually) is a
new adapter implementation, not a rewrite of subscription logic.
Webhooks (`checkout.session.completed`, `invoice.payment_failed`,
`customer.subscription.updated`, etc.) update `subscriptions` /
`usage_records` — the webhook handler is the *only* writer of billing
state derived from Stripe, so local state never drifts from two
different write paths.

**Critical separation (restated from 05 §4):** this billing system
(DataLume's SaaS revenue from the organisation) shares no table, no
service module and no code path with `commercial.payment_transactions`
(a tenant's rent paid to the landlord). Two Stripe-adjacent concepts,
zero shared code.

## 3. Entitlements enforcement

Entitlement checks happen at the same layer as permission and tenant
checks (all three are FastAPI dependencies composed on a route:
`tenant`, `permission`, `entitlement`), so a route like bulk XLSX import
can require `require_entitlement("bulk_import")` and cleanly return a
"upgrade your plan" response rather than a generic 403 that looks like an
authorisation bug.

## 4. API specification

Versioned, resource-oriented REST under `/api/v1/`, matching spec §69's
groups exactly, with the addition of `/api/v1/data-health` and
`/api/v1/audit` made explicit:

```
/api/v1/auth                 login, logout, session, mfa
/api/v1/organisations        CRUD, onboarding
/api/v1/workspaces           CRUD, adaptive layout resolution
/api/v1/developments          CRUD
/api/v1/buildings              CRUD
/api/v1/properties              CRUD, bulk
/api/v1/spaces                   CRUD
/api/v1/components                CRUD, lifecycle, planned-investment
/api/v1/references                 internal reference generation, external reference CRUD
/api/v1/specifications               CRUD, versions
/api/v1/documents                     upload, versions, download
/api/v1/building-control                CRUD
/api/v1/golden-thread                    read (composed view, see 03 §4)
/api/v1/changes                           change control CRUD, approve/reject
/api/v1/defects                            CRUD
/api/v1/warranties                          CRUD
/api/v1/handover                             readiness, authorise
/api/v1/repairs                               CRUD, repeat-repair signals
/api/v1/compliance                             frameworks, domains, requirements,
                                                inspections, actions, status
/api/v1/hazards                                 CRUD, damp-and-mould
/api/v1/tenancies                                CRUD
/api/v1/leases                                    CRUD
/api/v1/rent-obligations                           CRUD
/api/v1/payments                                    record, list (never charge — 05 §4)
/api/v1/arrears                                      snapshot, ageing
/api/v1/uploads                                       presigned URL, dataset lifecycle
/api/v1/datasets                                       list, mapping templates
/api/v1/analytics                                       cross-domain aggregates
/api/v1/attention                                        signals, ack/resolve
/api/v1/alerts                                            list, mark-read
/api/v1/ask                                                Ask DataLume
/api/v1/reports                                             generate, list, download
/api/v1/audit                                                read (permission-gated)
/api/v1/subscriptions                                         plan, checkout, portal, webhook
```

Every list endpoint is paginated (cursor-based, spec §72) and supports
server-side filtering — no endpoint returns an unbounded collection.
Every mutating endpoint requires `tenant` + `permission` (+ `entitlement`
where relevant) dependencies; this triple is enforced by a shared
`@protected_route(...)` decorator so a new endpoint author cannot forget
one without an explicit `# unscoped: <reason>` opt-out that a lint rule
flags for review.
