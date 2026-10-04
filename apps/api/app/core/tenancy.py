"""Session resolution, tenant scoping and permission enforcement.

Implements the two-layer tenant isolation and combined tenant+permission
dependency described in architecture/01-platform-foundations.md §1 and §3,
and architecture/07-platform-services.md §4."""

import hashlib
import uuid
from dataclasses import dataclass

import redis
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.models import Membership, MembershipStatus, Role, User
from app.auth.rbac import role_has_permission
from app.core.config import get_settings
from app.core.db import get_db

settings = get_settings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_current_user_context(db: Session, user_id: uuid.UUID) -> None:
    """Sets app.current_user_id — read by memberships' own RLS policy
    (migration 0027) alongside app.current_org_id, specifically so a
    user can see their own membership rows across every organisation
    they belong to (GET /auth/me's workspace-switcher list) without an
    org context to scope TenantScopedSession to. Same connection-scoped
    set_config pattern as TenantScopedSession (app/core/db.py's own
    "reset" pool-event listener resets this GUC too, for the same
    leak-between-requests reason) and the same SQLite no-op guard."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.current_user_id', :user_id, false)"), {"user_id": str(user_id)})


@dataclass
class AuthContext:
    user: User
    organisation_id: uuid.UUID | None
    membership: Membership | None
    role_code: str | None


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = redis_client.get(f"session:{hash_session_token(session_token)}")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    redis_client.expire(f"session:{hash_session_token(session_token)}", settings.session_ttl_seconds)
    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    _set_current_user_context(db, user.id)
    return user


def get_current_user_optional(
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db),
) -> User | None:
    """Same resolution as get_current_user, but returns None instead of
    raising — for the invitation-accept endpoint, which must work for a
    signed-out visitor (the common case) as well as someone already
    signed in under the invited email address."""
    if not session_token:
        return None
    user_id = redis_client.get(f"session:{hash_session_token(session_token)}")
    if not user_id:
        return None
    return db.get(User, uuid.UUID(user_id))


class TenantScopedSession:
    """Sets the Postgres session variable app.current_org_id (read by
    every tenant table's RLS policy — see alembic migration 0001) on an
    existing Session, scoped to exactly one organisation_id.

    Deliberately NOT a Session subclass/wrapper — get_tenant_db below
    returns the plain, same Session object back (not an instance of
    this class) specifically so every router's existing `db: Session =
    Depends(get_db)` becomes `Depends(get_tenant_db)` with no other
    change: no service function signature, no .add()/.flush()/
    .commit()/.get() call site anywhere has to change. This class is
    the one place that actually runs the SET — construct it for its
    side effect; nothing downstream needs to hold onto the instance."""

    def __init__(self, db: Session, organisation_id: uuid.UUID):
        self.db = db
        self.organisation_id = organisation_id
        # set_config() is Postgres-specific (no SQLite equivalent, and
        # no RLS for it to drive there anyway — see conftest.py's own
        # `client` fixture docstring: "RLS... is verified separately
        # against real Postgres"). Every other test in this suite runs
        # against the SQLite fixture, so this has to no-op there rather
        # than error, or wiring get_tenant_db into a router would break
        # every tenant-scoped SQLite test — the Postgres-only app-layer
        # effect this class exists for simply doesn't apply there.
        if db.get_bind().dialect.name != "postgresql":
            return
        # SET/SET LOCAL are Postgres utility statements, not ordinary
        # DML — they're parsed before the normal planner stage and
        # cannot take a bind parameter (`SET LOCAL x = $1` is a syntax
        # error at the protocol level, not just unusual style), hence
        # set_config() rather than either.
        #
        # is_local=FALSE (connection-scoped), not TRUE (SET LOCAL's own
        # transaction-scoped reset) — deliberately, after finding this
        # codebase commits mid-request in several places (e.g.
        # development/router.py's add_property: db.commit() then
        # db.refresh(prop)). A transaction-scoped setting resets the
        # instant that first commit happens, silently leaving every
        # query afterwards — still the same request — running with no
        # tenant context again, and RLS fails closed on exactly that
        # next query. A connection-scoped setting survives for the rest
        # of this request's connection checkout; app/core/db.py's own
        # "reset" pool-event listener is what stops it from then
        # leaking into whichever later, unrelated request happens to
        # reuse that same pooled connection next.
        self.db.execute(text("SELECT set_config('app.current_org_id', :org_id, false)"), {"org_id": str(organisation_id)})

    def query(self, *args, **kwargs):
        return self.db.query(*args, **kwargs)


def get_auth_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_organisation_id: uuid.UUID | None = Header(default=None),
) -> AuthContext:
    if x_organisation_id is None:
        return AuthContext(user=user, organisation_id=None, membership=None, role_code=None)

    # The real root of the bootstrap problem every fix elsewhere in
    # this module works around: this is the function that establishes
    # tenant context in the first place, so there is nothing to scope
    # to yet when this query runs — but it has to, because memberships
    # is RLS-protected and fails closed. Scoping to the *claimed*
    # x_organisation_id (straight from the request header, not yet
    # verified) before this lookup is safe: the query below is exactly
    # the check that decides whether that claim is legitimate, and RLS
    # can only narrow what it would already filter for
    # (Membership.organisation_id == x_organisation_id), never widen
    # it — a user with no real membership there still gets nothing
    # back, claim or no claim.
    TenantScopedSession(db, x_organisation_id)

    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.organisation_id == x_organisation_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active membership for this organisation")
    role = db.get(Role, membership.role_id)
    return AuthContext(
        user=user,
        organisation_id=x_organisation_id,
        membership=membership,
        role_code=role.code if role else None,
    )


def get_tenant_db(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Session:
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    TenantScopedSession(db, ctx.organisation_id)
    return db


def require_permission(permission: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.organisation_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
        if ctx.role_code is None or not role_has_permission(ctx.role_code, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return ctx

    return dependency
