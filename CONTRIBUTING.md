# Contributing to DataLume

This is a from-scratch build of a multi-tenant property intelligence
platform, developed sprint by sprint against a fixed architecture pack.
Before changing anything, read in this order:

1. [`README.md`](README.md) — what this is and how to run it.
2. [`architecture/`](architecture) — the authoritative design spec, one
   file per domain (`00` executive summary through `09` security/ops,
   `10` the sprint roadmap and acceptance matrix). If a change
   contradicts something here, the architecture doc is what needs to
   change first, not just the code.
3. [`STATUS.md`](STATUS.md) — the full build history: what's actually
   built and verified per sprint, real bugs found and fixed, and an
   honest list of what's unverified or out of scope in this
   environment (Postgres RLS, real load testing, a real backup drill,
   full OTel/Sentry tracing, a Playwright E2E suite). Don't assume
   something works because the architecture doc describes it — check
   STATUS.md for whether it was actually built and tested.

## Principles this codebase actually enforces

These aren't aspirational — every domain in this repo is built this
way, and a change that violates one of these should be treated as a
bug, not a style preference:

- **Deterministic analytics, never LLM-invented figures.** Compliance
  status, repeat-repair detection, handover readiness, arrears ageing,
  planned-investment scoring — all computed by plain, versioned,
  testable Python functions. "Ask DataLume" (`app/intelligence/ask/`)
  only ever interprets typed tool results a deterministic pipeline
  already produced; it never gets database access and tool *selection*
  is deterministic application code, not the model's own judgement.
- **Tenant isolation on every query, never frontend filtering alone.**
  Every domain route resolves through `get_auth_context`/
  `require_permission` (`app/core/tenancy.py`), and every query is
  scoped by `organisation_id`. See
  `app/tests/test_security_tenant_isolation.py` for the systematic
  cross-org fuzz suite — a new resource type should be added to that
  suite's registry, not just spot-checked once.
- **Full provenance and audit on writes and exports.** Domain records
  use `ProvenanceMixin` (source, import job, created/updated by+when);
  state-changing writes and any export/report-download endpoint call
  `record_audit_event` (`app/platform/audit.py`).
- **Adapter boundary + Null fallback for external services**, not a
  fake implementation. See `app/integrations/billing_provider.py`
  (Stripe) and `app/integrations/llm_provider.py` (Anthropic): a
  `Protocol`, a `Null*Provider` that raises a clear "not configured"
  error, and a real implementation behind a settings flag. Never stub
  out an integration with hardcoded fake data.
- **A feature isn't done because a screen exists.** Definition of done
  = frontend + backend + database + auth/tenant isolation + validation
  + provenance + audit + tests + real data flow + loading/empty states.

## Code conventions

**Backend** (`apps/api/app/<domain>/`): `models.py` / `schemas.py` /
`service.py` (pure business logic, no HTTP) / `router.py` (HTTP layer,
permission checks, calls into `service.py`). Migrations live in
`apps/api/alembic/versions/`, one file per schema change, paired with
the sprint that introduced it.

**Frontend** (`apps/web/src/app/(app)/`): shared primitives in
`components/` — `StatusBadge` is the only sanctioned way to render a
status indicator (colour + icon + text, never colour alone), and
`formStyles.ts` holds the shared input/button styles. Every `<label>`
needs a matching `id`/`htmlFor` on its control (or `aria-label` if
there's no visible label text) — this was a real, repo-wide bug found
and fixed once already; don't reintroduce it.

## Tests

```bash
cd apps/api && pytest          # every new endpoint needs at minimum:
                                #   - a happy-path test
                                #   - a permission-boundary test (if it's gated)
                                #   - a cross-org 404 test
cd apps/web && npm run build && npm run lint
```

For anything touching the browser (a new page, a changed flow), verify
it live — start the dev server and click through it — rather than
relying on the build/lint passing. STATUS.md's sprint write-ups
describe the smoketest pattern (SQLite + in-process fake Redis, no
Docker needed) used throughout this build for that.

## Commit style

A commit message should explain *why*, not restate the diff — see the
existing log for the pattern (e.g. `ede2b27`, `172bef5`, `f9abcb8`). If
a change fixes a bug found while building something else, say what the
bug actually was and how it was caught, not just "fix bug."

## Documentation

If a change adds or changes real behaviour, update `STATUS.md` (and
`architecture/10-roadmap-and-acceptance.md` if it affects the roadmap
summary) in the same commit or PR — this repo's history is only useful
if it stays accurate. If something is deliberately out of scope, say
so explicitly and why, rather than leaving it silently unimplemented.
