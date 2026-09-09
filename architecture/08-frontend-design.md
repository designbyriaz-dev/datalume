# 08 — Web Frontend: Screen Map, Design System, Accessibility, Performance

Covers spec items 66–67, 73, and `docs/DESIGN_SYSTEM.md`.

## 1. Screen map

```
(marketing)/                     — dark theme, logged out
  /                               marketing landing
  /pricing
  /sign-in                       split-screen dark auth (Sign In tab)
  /sign-up                       split-screen dark auth (Create Account tab)

(app)/                           — light theme, authenticated, tenant-scoped
  /home                          Home dashboard (see DESIGN_SYSTEM §4)
  /developments                  list + detail (hierarchy drill-down)
  /developments/[id]/handover    handover readiness
  /buildings/[id]
  /properties                    list, filters, bulk actions
  /properties/[id]                Property 360
  /components                      register, filters
  /components/[id]                  lifecycle detail
  /defects-warranties
  /repairs
  /compliance                        domain overview, per-domain drill-down
  /compliance/[domain]
  /safety                             hazards, damp & mould
  /stock-condition
  /planned-investment
  /tenancies
  /leases
  /rent-and-payments
  /arrears
  /data-and-uploads                    dataset list, mapping review, import history
  /reports
  /ask                                   Ask DataLume full-screen chat
  /organisation                           org profile, workspaces
  /organisation/users                      membership, roles
  /organisation/billing                     plan, invoices, portal link
  /settings
```

Navigation items actually rendered in the sidebar are the output of
`AdaptiveWorkspaceResolver` (01 §5) filtered by the caller's RBAC
permissions — the route tree above is the full superset; any given user
sees a subset.

## 2. Design tokens

Implemented as CSS custom properties + a Tailwind theme extension, one
source of truth in `apps/web/src/styles/tokens.css`, consumed by both the
light app shell and dark marketing/auth shell (never redefined ad hoc per
component — spec: "no ad-hoc inline colors" carried over from the mobile
build prompt's same rule, applied here too):

```css
:root {
  --color-primary: #2563EB;
  --color-primary-hover: #1D4ED8;
  --color-accent-cyan: #06B6D4;
  --color-success: #10B981;
  --color-warning: #F59E0B;
  --color-critical: #EF4444;
  --color-purple-accent: #7C3AED;

  --bg-app: #F8FAFC;
  --bg-card: #FFFFFF;
  --border-subtle: #E5E7EB;
  --text-primary: #0F172A;
  --text-secondary: #64748B;

  --bg-dark: #0B1220;
  --text-on-dark: #FFFFFF;
  --text-on-dark-muted: #94A3B8;

  --radius-card: 14px;
}
```

**Decision:** the light app shell and dark marketing/auth shell are two
explicit, separately-composed layout roots (`(app)/layout.tsx` vs
`(marketing)/layout.tsx`), not one theme with a dark-mode toggle.
**Rationale:** `DESIGN_SYSTEM.md` §6 is explicit — these are "two
distinct, intentional modes... do not blend them." A single toggle-based
theme would make it easy to accidentally leak dark-hero styling into the
authenticated shell; separate layout roots make that a structural
impossibility rather than a discipline problem.

## 3. Component inventory (shared, design-system-owned)

`components/`: `Sidebar`, `TopBar`, `KpiStatCard` (icon + value + label +
trend delta), `StatusBadge` (colour + icon + text label — never colour
alone, spec §73/DESIGN_SYSTEM §6), `TrendLineChart`, `DonutChart`,
`AskDataLumePanel`, `AttentionTable`, `DataQualityBreakdown` (donut +
horizontal progress bars), `RecentUploadsTable`, `RiskAreaBarList`,
`PromoCard`, `GroundedClaim` (mirrors the mobile app's component of the
same name — separates observed fact from AI interpretation, spec §58),
`AuthCard` (tab switcher, OAuth buttons, trust badges).

## 4. Accessibility

Enforced, not aspirational: semantic landmarks (`nav`, `main`, `aside`),
full keyboard operability including the `⌘K` search and chart
interactions, visible focus rings (never `outline: none` without a
replacement), WCAG AA contrast checked in CI (`axe-core` in Playwright
e2e), form fields with associated `<label>`/`aria-describedby` errors,
and — the specific rule called out twice in the source material — every
status/priority indicator pairs colour with an icon and/or text label,
enforced by `StatusBadge` being the only sanctioned way to render status
(no raw coloured `<span>` in domain screens).

## 5. Performance

Server-rendered list pages with cursor pagination and server-side
filtering (matches API design in 07 §4) — no client-side loading of full
portfolios. Charts render from pre-aggregated API responses, never raw
row-level data shipped to the browser. Route-level code splitting via the
Next.js App Router by default; heavy chart libraries lazy-loaded on the
routes that use them.
