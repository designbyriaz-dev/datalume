from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)


class _RequestSession(Session):
    """A Session bound to one explicitly-held Connection for its whole
    life, rather than SQLAlchemy's default of lazily re-acquiring a
    (possibly different) connection from the pool after every commit.

    Why this matters here specifically: TenantScopedSession sets
    app.current_org_id on whichever physical connection is live at that
    moment. A plain `sessionmaker(bind=engine)` session releases its
    connection back to the pool on every commit and re-acquires one —
    not necessarily the same one — on the next query, so a single
    request that commits mid-way (common in this codebase — e.g.
    development/router.py's add_property: db.commit() then
    db.refresh(prop)) could silently end up running its next query on
    an entirely different, never-scoped connection. Confirmed by hand:
    this exact scenario broke scripts/seed_demo.py (RLS-blocked
    db.refresh on a freshly-committed Development) even after the
    connection-scoped set_config fix in tenancy.py, specifically
    because that fix assumed one request keeps one connection
    throughout — an assumption nothing enforced until this class.

    close() releases the held connection back to the pool itself
    (Session.close() alone does not, when bound to a Connection rather
    than an Engine) — which is what lets app/core/db.py's own "reset"
    pool-event listener do its job on checkin, same as before."""

    def __init__(self, **kwargs):
        self._tenancy_connection = engine.connect()
        super().__init__(bind=self._tenancy_connection, **kwargs)

    def close(self):
        super().close()
        self._tenancy_connection.close()


def SessionLocal() -> Session:
    return _RequestSession(autoflush=False, autocommit=False)


# TenantScopedSession (app/core/tenancy.py) sets app.current_org_id via
# set_config(..., is_local=false) — connection-scoped, not transaction-
# scoped, deliberately: this codebase commits mid-request in several
# places (e.g. development/router.py's add_property does db.commit()
# then db.refresh(prop)), and a transaction-scoped (is_local=true)
# setting resets the instant that first commit happens, silently
# leaving every query afterwards running with no tenant context again
# — RLS then fails closed on the very next query, not open, so this
# surfaced as a 500 on refresh rather than a leak, but it's the same
# underlying gap. A connection-scoped setting survives exactly as long
# as this one request holds the connection — but pooled connections are
# reused by later, unrelated requests, and a plain ROLLBACK on checkin
# (SQLAlchemy's pool default) does NOT clear a non-local SET. Without
# this listener, a connection could carry one request's organisation_id
# into the next request that happens to reuse it. RESET on every
# checkin, for every connection, closes that gap the same way a
# connection pool should never leak any other kind of per-request state.
@event.listens_for(engine, "reset")
def _reset_tenant_context(dbapi_connection, connection_record, reset_state):
    if engine.dialect.name != "postgresql":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("RESET app.current_org_id")
        # app.current_user_id (app/core/tenancy.py's _set_current_user_
        # context, migration 0027) is the same connection-scoped GUC
        # pattern, for the same reason — memberships' RLS policy reads
        # it to let a user see their own cross-org membership rows, and
        # it needs the same reset-on-checkin or it leaks the same way.
        cursor.execute("RESET app.current_user_id")
    finally:
        cursor.close()
    # RESET runs inside whatever transaction block is already open on
    # this connection at checkin time, not as an autocommitted DDL-like
    # statement — without committing it here, it has no effect: a later
    # rollback on this same connection (its own, or implicitly on next
    # checkout) would undo the RESET along with it, and the org id that
    # was supposedly cleared comes right back. Confirmed by hand: this
    # exact scenario silently failed to clear the GUC until this commit
    # was added.
    dbapi_connection.commit()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """Plain, unscoped session — used by auth/session resolution itself
    (before we know which organisation the caller belongs to, e.g.
    signup/login), a handful of genuinely cross-tenant or pre-auth
    routes (billing's /plans catalog and Stripe webhook, invitation
    lookup/accept), and platform-admin tooling. Every other domain
    route uses get_tenant_db (core/tenancy.py) instead."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
