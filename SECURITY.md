# Security Policy

## Project status

DataLume is a from-scratch demo/prototype build (see
[`STATUS.md`](STATUS.md) for the full sprint-by-sprint history). It is
**not a live production service** — there is no deployed instance
handling real tenant, resident, or compliance data. The two seeded
demo organisations (Northstar Housing, Northstar Commercial) contain
only fictional, synthetic data.

That said, the codebase implements real multi-tenant isolation,
authentication, and authorization, and is intended to be built on
toward a real pilot — so security issues in it are still worth
reporting and fixing properly.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for a security
vulnerability. Instead, email **designbyriaz@gmail.com** with:

- A description of the issue and its potential impact.
- Steps to reproduce it (a minimal repro is ideal).
- Which part of the system it affects (API route, frontend page,
  worker job, etc.).

You should get an acknowledgement within a few days. There's no
established SLA or bug bounty for this project — it's maintained by
one person on a demo/prototype basis — but real reports will be taken
seriously and fixed.

## What's already known

Before reporting, it's worth checking whether the issue is already a
documented, known gap:

- [`architecture/09-security-testing-ops.md`](architecture/09-security-testing-ops.md) —
  the threat model this build was designed against (tenant isolation,
  role escalation, AI grounding, file upload, secrets in logs, webhook
  spoofing, SSRF, and more), with each threat's primary mitigation.
- [`STATUS.md`](STATUS.md)'s "Not yet done" section — the current,
  honest list of what's unverified or explicitly out of scope in this
  environment. Notably:
  - **Postgres Row-Level Security is unverified against a real
    database.** Application-layer tenant isolation (query scoping +
    membership checks) is covered by
    `apps/api/app/tests/test_security_tenant_isolation.py` and passes,
    but this project has never run against real Postgres, so the RLS
    policies themselves (the second of the two tenant-isolation
    layers) are unconfirmed.
  - No CI pipeline is wired up yet, so nothing currently gates merges
    on the security test suite running green.
  - Stripe billing and full OTel/Sentry tracing are not wired up to
    real external services (see `app/integrations/` for the adapter
    boundaries and `Null*` fallbacks in use instead).

If your finding is about one of these already-documented gaps, feel
free to open a normal GitHub issue instead of emailing — it isn't a
disclosure, since it's already written up.

## Supported versions

There are no released versions or version branches — this is a single
`main` branch under active development. Security fixes land on `main`.
