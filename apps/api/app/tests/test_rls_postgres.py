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
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.provenance import SourceType
from app.core.tenancy import TenantScopedSession
from app.development.models import Property
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
    becoming a cross-tenant data leak instead of an empty result."""
    org_a = _make_org(pg_session, "RLS Fail-Closed Test Org")
    scoped_a = TenantScopedSession(pg_session, org_a.id)
    scoped_a.db.add(
        Property(id=uuid.uuid4(), organisation_id=org_a.id, property_reference="RLS-FC-1", address="x", source_type=SourceType.MANUAL)
    )
    pg_session.commit()

    # A fresh connection/transaction with app.current_org_id unset —
    # SET LOCAL is transaction-scoped, so committing above already
    # ended the prior transaction's setting.
    assert pg_session.query(Property).filter(Property.property_reference == "RLS-FC-1").all() == []
