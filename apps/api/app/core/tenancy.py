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
    """Wraps a SQLAlchemy Session bound to exactly one organisation_id.

    Sets the Postgres session variable app.current_org_id (read by every
    tenant table's RLS policy — see alembic migration 0001) AND is the
    only session type domain services are allowed to accept, so a query
    written without going through this class is a type error, not just a
    convention. Two enforcement layers for the same invariant, per
    architecture 01 §1."""

    def __init__(self, db: Session, organisation_id: uuid.UUID):
        self.db = db
        self.organisation_id = organisation_id
        self.db.execute(text("SET LOCAL app.current_org_id = :org_id"), {"org_id": str(organisation_id)})

    def query(self, *args, **kwargs):
        return self.db.query(*args, **kwargs)


def get_auth_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_organisation_id: uuid.UUID | None = Header(default=None),
) -> AuthContext:
    if x_organisation_id is None:
        return AuthContext(user=user, organisation_id=None, membership=None, role_code=None)

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
) -> TenantScopedSession:
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return TenantScopedSession(db, ctx.organisation_id)


def require_permission(permission: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.organisation_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
        if ctx.role_code is None or not role_has_permission(ctx.role_code, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return ctx

    return dependency
