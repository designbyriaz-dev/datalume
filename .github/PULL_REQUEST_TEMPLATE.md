## What & why

<!-- What does this change, and why — link an issue/sprint if relevant.
     Explain the reasoning, not just a restatement of the diff. -->

## Checklist

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the conventions this
checklist is drawn from.

- [ ] New/changed endpoints have: a happy-path test, a permission-
      boundary test (if gated), and a cross-org 404 test
- [ ] Tenant isolation preserved — every query still scopes by
      `organisation_id`; a new GET-by-id resource type is added to
      `app/tests/test_security_tenant_isolation.py`'s registry
- [ ] Writes/exports that should be audited call `record_audit_event`
- [ ] `cd apps/api && pytest` passes
- [ ] `cd apps/web && npm run build && npm run lint` pass (if the
      frontend changed)
- [ ] Any new `<label>` has a matching `id`/`htmlFor` (or `aria-label`
      if there's no visible label text)
- [ ] Verified live in the browser, not just build/lint (for anything
      that touches a page or user flow)
- [ ] `STATUS.md` updated (and `architecture/10-roadmap-and-
      acceptance.md` too, if this affects the roadmap summary)
- [ ] If something here is deliberately out of scope, that's said
      explicitly rather than left silently unimplemented

## How this was tested

<!-- Commands run, scenarios clicked through, what you saw. -->
