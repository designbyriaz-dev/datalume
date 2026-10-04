"""Real Postgres Row Level Security verification — architecture
01-platform-foundations.md §1's two-layer tenant isolation, second
layer. Every other test in this suite runs against SQLite
(app/tests/conftest.py's own docstring: "RLS... is verified separately
against real Postgres"), where SQLite's complete absence of RLS support
makes this layer untestable — it is a real Postgres feature, not
something a fixture can fake.

This module connects to a real Postgres directly (bypassing the
SQLite-only `client` fixture entirely) and drives the exact same
TenantScopedSession class (app/core/tenancy.py) every real request
goes through, rather than hand-rolled SQL — so this proves the
production code path, not just the underlying Postgres mechanism in
isolation.

Skips cleanly (not a failure) unless DATABASE_URL is set to a real,
reachable Postgres with the schema already migrated — the default
`pytest -q` run (no DATABASE_URL override) is unaffected. CI's
dedicated `rls` job (see .github/workflows/ci.yml) sets DATABASE_URL to
a real `postgres:` service container and runs `alembic upgrade head`
against it first, so this suite now runs for real on every push, not
just when a developer happens to have Postgres installed locally.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

import app.core.db as db_module
from app.core.provenance import SourceType
from app.core.tenancy import TenantScopedSession
from app.development.models import Property
from app.main import app
from app.organisations.models import Organisation, OrganisationType

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _real_postgres_available() -> bool:
    if not DATABASE_URL.startswith("postgresql"):
        return False
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect():
            pass
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _real_postgres_available(),
    reason="DATABASE_URL isn't set to a reachable real Postgres — RLS is a Postgres-only feature, "
    "see this module's own docstring for why these tests can't run against the SQLite fixture.",
)


@pytest.fixture()
def pg_session():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def pg_client(monkeypatch, tmp_path):
    """Same shape as conftest.py's SQLite `client` fixture (fake Redis,
    local-disk document storage), but bound to the real Postgres this
    module already requires — so a real HTTP request through a real
    router, via get_tenant_db, can be proven end to end, not just the
    lower-level TenantScopedSession mechanism the tests above exercise
    directly."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[db_module.get_db] = override_get_db

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def set(self, key, value, ex=None):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def expire(self, key, ttl):
            pass

        def delete(self, key):
            self.store.pop(key, None)

    import app.auth.router as auth_router_module
    import app.core.request_logging as request_logging_module
    import app.core.tenancy as tenancy_module

    fake_redis = FakeRedis()
    monkeypatch.setattr(tenancy_module, "redis_client", fake_redis)
    monkeypatch.setattr(auth_router_module, "redis_client", fake_redis)
    monkeypatch.setattr(request_logging_module, "redis_client", fake_redis)

    import app.documents.router as documents_router_module
    import app.ingestion.router as ingestion_router_module
    import app.reports.router as reports_router_module
    import app.reports.service as reports_service_module
    from app.integrations.storage import LocalFilesystemStorage

    test_storage = LocalFilesystemStorage(tmp_path / "storage")
    monkeypatch.setattr(documents_router_module, "get_document_storage", lambda: test_storage)
    monkeypatch.setattr(ingestion_router_module, "get_document_storage", lambda: test_storage)
    monkeypatch.setattr(reports_service_module, "get_document_storage", lambda: test_storage)
    monkeypatch.setattr(reports_router_module, "get_document_storage", lambda: test_storage)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _signup(pg_client, org_name: str) -> str:
    resp = pg_client.post(
        "/api/v1/auth/signup",
        json={
            "name": "RLS E2E Tester",
            "email": f"rls-e2e-{uuid.uuid4().hex[:12]}@example.com",
            "password": "correct-horse-battery",
            "organisation_name": org_name,
            "organisation_type": "HOUSING_ASSOCIATION",
            "goals": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["organisation_id"]


def _make_org(pg_session, name: str) -> Organisation:
    org = Organisation(
        id=uuid.uuid4(),
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        organisation_type=OrganisationType.HOUSING_ASSOCIATION,
    )
    pg_session.add(org)
    pg_session.commit()
    return org


def test_a_tenant_scoped_session_only_sees_its_own_organisations_rows(pg_session):
    org_a = _make_org(pg_session, "RLS Test Org A")
    org_b = _make_org(pg_session, "RLS Test Org B")

    scoped_a = TenantScopedSession(pg_session, org_a.id)
    scoped_a.db.add(
        Property(id=uuid.uuid4(), organisation_id=org_a.id, property_reference="RLS-A-1", address="Org A's property", source_type=SourceType.MANUAL)
    )
    pg_session.commit()

    # Org A sees exactly its own row.
    scoped_a_again = TenantScopedSession(pg_session, org_a.id)
    assert [p.property_reference for p in scoped_a_again.query(Property).all()] == ["RLS-A-1"]

    # Org B — same table, same data physically present — sees nothing.
    # This is the actual proof: it isn't that Org B has no properties,
    # it's that Postgres itself refuses to return Org A's row to a
    # session scoped to a different organisation_id.
    scoped_b = TenantScopedSession(pg_session, org_b.id)
    assert scoped_b.query(Property).all() == []


def test_rls_rejects_a_cross_tenant_write_at_the_database_level(pg_session):
    org_a = _make_org(pg_session, "RLS Write Test Org A")
    org_b = _make_org(pg_session, "RLS Write Test Org B")

    # Scoped to Org A, but the row itself claims to belong to Org B —
    # the application layer would never construct this (every service
    # function takes organisation_id from the scoped session itself),
    # but RLS has to hold even if a future bug, a raw migration script,
    # or a compromised app layer ever did. This is exactly the scenario
    # the two-layer design exists for.
    scoped_a = TenantScopedSession(pg_session, org_a.id)
    scoped_a.db.add(
        Property(id=uuid.uuid4(), organisation_id=org_b.id, property_reference="RLS-SNEAKY", address="Should never be written", source_type=SourceType.MANUAL)
    )
    with pytest.raises(DBAPIError, match="row-level security"):
        pg_session.commit()
    pg_session.rollback()


def test_rls_fails_closed_with_no_tenant_context_set(pg_session):
    """A plain session with app.current_org_id never set at all (no
    TenantScopedSession wrapper) must see nothing — not everything.
    Fail-closed is the only safe default for a multi-tenant system;
    this is what stops a code path that forgets to scope a query from
    becoming a cross-tenant data leak instead of an empty result.

    Uses a genuinely separate engine/connection from pg_session's own —
    TenantScopedSession sets app.current_org_id connection-scoped, not
    transaction-scoped (see its own docstring for why), so it would
    still be set on pg_session's own connection even after a commit;
    the real guarantee under test is that a connection nobody has ever
    scoped sees nothing, not that one commit un-scopes a connection
    that was."""
    org_a = _make_org(pg_session, "RLS Fail-Closed Test Org")
    scoped_a = TenantScopedSession(pg_session, org_a.id)
    scoped_a.db.add(
        Property(id=uuid.uuid4(), organisation_id=org_a.id, property_reference="RLS-FC-1", address="x", source_type=SourceType.MANUAL)
    )
    pg_session.commit()

    fresh_engine = create_engine(DATABASE_URL)
    FreshSessionLocal = sessionmaker(bind=fresh_engine, autoflush=False, autocommit=False)
    fresh_session = FreshSessionLocal()
    try:
        assert fresh_session.query(Property).filter(Property.property_reference == "RLS-FC-1").all() == []
    finally:
        fresh_session.close()
        fresh_engine.dispose()


def test_rls_context_does_not_leak_to_a_connection_reused_by_a_different_org():
    """The other half of the connection-scoped tradeoff: a pooled
    connection that WAS scoped to Org A must not carry that into
    whichever later caller reuses it next, unless that caller sets its
    own context first — app/core/db.py's "reset" pool-event listener is
    what's supposed to guarantee this. Uses app.core.db.engine itself
    (not a throwaway engine of this test's own) — the listener is
    registered on that specific Engine instance, so a separately
    constructed one would prove nothing about the real app's behaviour.
    Forces the same physical connection to be reused by checking it
    back into the pool (Session.close()) and acquiring a new Session
    from the same engine with nothing else competing for a connection
    in between — QueuePool hands back the most recently returned
    connection first when only one is checked out at a time."""
    import app.core.db as db_module

    SessionLocal = sessionmaker(bind=db_module.engine, autoflush=False, autocommit=False)

    first = SessionLocal()
    org_a = _make_org(first, "RLS Reset Test Org A")
    scoped_a = TenantScopedSession(first, org_a.id)
    scoped_a.db.add(
        Property(id=uuid.uuid4(), organisation_id=org_a.id, property_reference="RLS-RESET-1", address="x", source_type=SourceType.MANUAL)
    )
    first.commit()
    first.close()  # returns the connection to the pool — must trigger the reset listener

    second = SessionLocal()
    try:
        # No TenantScopedSession on `second` at all — if the reset
        # listener didn't run, this connection would still think it's
        # Org A and leak Org A's row to whatever unrelated query runs
        # here next.
        assert second.query(Property).filter(Property.property_reference == "RLS-RESET-1").all() == []
    finally:
        second.close()


def test_a_real_api_request_through_a_real_router_is_rls_scoped(pg_client):
    """The other tests above drive TenantScopedSession directly — real,
    but one level removed from proving get_tenant_db is actually wired
    into a router's FastAPI dependency chain for a genuine HTTP request.
    This drives the full real path: two real signups, a real POST
    through app/development/router.py's add_property (Depends
    (get_tenant_db) as of this change), and a real GET as a different
    org's user — proving the wiring itself, not just the mechanism."""
    org_a_id = _signup(pg_client, "RLS E2E Org A")
    create_resp = pg_client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_a_id}, json={"address": "RLS E2E Org A's property"}
    )
    assert create_resp.status_code == 201, create_resp.text

    # A real property, genuinely visible to the org that owns it.
    own_list = pg_client.get("/api/v1/properties", headers={"X-Organisation-Id": org_a_id})
    assert len(own_list.json()) == 1

    # A second real signup — a different user, different organisation,
    # same physical properties table. The new session cookie replaces
    # the first (TestClient keeps one cookie jar), exactly like a
    # second real browser logging in as someone else.
    org_b_id = _signup(pg_client, "RLS E2E Org B")
    cross_tenant_list = pg_client.get("/api/v1/properties", headers={"X-Organisation-Id": org_b_id})
    assert cross_tenant_list.status_code == 200
    assert cross_tenant_list.json() == []


def test_report_worker_processes_a_job_created_through_a_real_request(pg_client):
    """report_jobs is RLS-protected, and the worker's own job-discovery
    query (process_pending_report_jobs) has no single organisation to
    scope to — it serves every org on each tick — so before the fix in
    app/worker/jobs/report_generation.py, this query silently returned
    nothing, for any organisation, forever: a report requested through
    the real API would sit PENDING and never move, with no error
    anywhere. Proves the actual fix: a real job, requested through a
    real HTTP request, genuinely gets picked up and finished by the
    real worker function run directly against this same database."""
    org_id = _signup(pg_client, "RLS Report Worker Org")
    resp = pg_client.post(
        "/api/v1/reports",
        headers={"X-Organisation-Id": org_id},
        json={"report_type": "DEVELOPMENT_SUMMARY", "format": "CSV"},
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["id"]
    assert resp.json()["status"] == "PENDING"

    from app.worker.jobs.report_generation import process_pending_report_jobs

    engine = create_engine(DATABASE_URL)
    worker_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        result = process_pending_report_jobs(worker_session)
        assert result.jobs_processed >= 1
    finally:
        worker_session.close()
        engine.dispose()

    status_resp = pg_client.get(f"/api/v1/reports/{job_id}", headers={"X-Organisation-Id": org_id})
    assert status_resp.json()["status"] == "READY"


def test_many_sequential_requests_each_commit_and_refresh_correctly(pg_client):
    """Regression guard for the bug scripts/seed_demo.py's own real run
    found: TenantScopedSession's connection-scoped set_config
    (is_local=false) only holds if the *same* request keeps the *same*
    physical connection for its whole lifetime — true for a plain
    sessionmaker(bind=engine) session only by luck of low pool
    contention (a single isolated test, like the one above creating one
    property, can pass even when the underlying assumption is false,
    because nothing else is competing for a connection to get handed
    back instead). The real seed script — several POST requests in a
    row against the same org, exactly like this test — hit it for
    real: add_development's db.commit() then db.refresh(dev) failed
    with "Could not refresh instance" on what was, by then, an
    unscoped connection. app/core/db.py's _RequestSession (binding each
    request's Session to one explicitly-held Connection instead of
    letting SQLAlchemy silently swap connections between transactions)
    is what actually fixes this; this test is what makes sure it stays
    fixed, since a single-request test alone wouldn't reliably catch a
    regression here either."""
    org_id = _signup(pg_client, "RLS Sequential Commits Org")
    for i in range(5):
        resp = pg_client.post(
            "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": f"Development {i}"}
        )
        assert resp.status_code == 201, resp.text

    list_resp = pg_client.get("/api/v1/developments", headers={"X-Organisation-Id": org_id})
    assert len(list_resp.json()) == 5


def test_me_shows_a_users_own_memberships_without_leaking_anyone_elses(pg_client):
    """migration 0027's own real-world trigger: logging in against a
    freshly backup-restored database and calling the real /me endpoint
    returned memberships: [] — memberships is RLS-protected and /me's
    own query deliberately has no single organisation to scope to (it
    spans every org the user belongs to, for the workspace switcher).
    Proves both directions of the fix: a user's own cross-org
    memberships become visible (the bug), and this doesn't leak into
    either another user's own /me or an org's member roster (the risk
    a less careful fix could have introduced — organisations/
    router.py's list_members stays additionally filtered by
    organisation_id at the app layer regardless of what memberships'
    RLS policy allows through)."""
    password = "correct-horse-battery"
    email_a = f"rls-me-a-{uuid.uuid4().hex[:12]}@example.com"
    email_b = f"rls-me-b-{uuid.uuid4().hex[:12]}@example.com"

    signup_a = pg_client.post(
        "/api/v1/auth/signup",
        json={
            "name": "User A",
            "email": email_a,
            "password": password,
            "organisation_name": "RLS Me Fix Org A",
            "organisation_type": "HOUSING_ASSOCIATION",
            "goals": [],
        },
    )
    org_a_id = signup_a.json()["organisation_id"]

    signup_b = pg_client.post(
        "/api/v1/auth/signup",
        json={
            "name": "User B",
            "email": email_b,
            "password": password,
            "organisation_name": "RLS Me Fix Org B",
            "organisation_type": "HOUSING_ASSOCIATION",
            "goals": [],
        },
    )
    org_b_id = signup_b.json()["organisation_id"]

    # Still signed in as User B (the TestClient's one cookie jar) — the
    # bug this migration fixes: User B's own /me must show their own
    # Org B membership, not an empty list.
    me_b = pg_client.get("/api/v1/auth/me").json()
    assert [m["organisation_id"] for m in me_b["memberships"]] == [org_b_id]

    # Switch back to User A and confirm the same holds for them, with
    # no sign of User B's membership anywhere in it.
    pg_client.post("/api/v1/auth/login", json={"email": email_a, "password": password})
    me_a = pg_client.get("/api/v1/auth/me").json()
    assert [m["organisation_id"] for m in me_a["memberships"]] == [org_a_id]

    # The no-leak direction: Org A's own member roster must show only
    # User A — the widened memberships policy must never let User B's
    # row bleed into a query that's scoped to Org A.
    roster = pg_client.get("/api/v1/organisations/members", headers={"X-Organisation-Id": org_a_id})
    assert [m["email"] for m in roster.json()] == [email_a]
