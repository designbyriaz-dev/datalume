import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.models import Invitation, InvitationStatus, Membership, MembershipStatus, Role, User
from app.auth.rbac import SYSTEM_ROLE_CODES
from app.auth.router import _get_or_create_role, _issue_session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_password
from app.core.tenancy import AuthContext, get_auth_context, get_current_user_optional, require_permission
from app.organisations.adaptive import WorkspaceLayout, resolve_workspace_layout
from app.organisations.models import Organisation
from app.organisations.schemas import (
    AcceptInvitationRequest,
    InvitationOut,
    InviteMemberRequest,
    MemberOut,
    PublicInvitationOut,
)
from app.platform.audit import record_audit_event

router = APIRouter(prefix="/api/v1/workspaces", tags=["organisations"])
members_router = APIRouter(prefix="/api/v1/organisations", tags=["organisations"])
invitations_router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])
settings = get_settings()

INVITATION_TTL_DAYS = 7


@router.get("/layout", response_model=WorkspaceLayout)
def get_workspace_layout(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    org = db.get(Organisation, ctx.organisation_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return resolve_workspace_layout(org.organisation_type, org.goals)


# --- Members & invitations -------------------------------------------------
# "org.manage_members" is deliberately absent from every ROLE_PERMISSIONS
# set in app/auth/rbac.py except via the OWNER/ADMIN wildcard ("*") — same
# convention as "billing.manage" (app/platform/router.py): a permission
# string that exists only to be granted by the wildcard, not spelled out
# per role.


def _invitation_out(invitation: Invitation, role_code: str) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role_code=role_code,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
        invite_url=f"{settings.web_app_url}/accept-invite?token={invitation.token}",
    )


def _resolve_pending_invitation(db: Session, token: str) -> Invitation:
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    if invitation.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status.HTTP_410_GONE, "This invitation has already been accepted")
    if invitation.status == InvitationStatus.REVOKED:
        raise HTTPException(status.HTTP_410_GONE, "This invitation has been revoked")
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if invitation.status == InvitationStatus.PENDING and expires_at < datetime.now(timezone.utc):
        invitation.status = InvitationStatus.EXPIRED
        db.commit()
        raise HTTPException(status.HTTP_410_GONE, "This invitation has expired")
    return invitation


@members_router.get("/members", response_model=list[MemberOut])
def list_members(
    ctx: AuthContext = Depends(require_permission("org.manage_members")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Membership, User, Role)
        .join(User, Membership.user_id == User.id)
        .join(Role, Membership.role_id == Role.id)
        .filter(Membership.organisation_id == ctx.organisation_id)
        .order_by(Membership.created_at)
        .all()
    )
    return [
        MemberOut(user_id=user.id, name=user.name, email=user.email, role_code=role.code, status=membership.status.value)
        for membership, user, role in rows
    ]


@members_router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    ctx: AuthContext = Depends(require_permission("org.manage_members")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Invitation, Role)
        .join(Role, Invitation.role_id == Role.id)
        .filter(Invitation.organisation_id == ctx.organisation_id, Invitation.status == InvitationStatus.PENDING)
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return [_invitation_out(invitation, role.code) for invitation, role in rows]


@members_router.post("/invitations", status_code=status.HTTP_201_CREATED, response_model=InvitationOut)
def create_invitation(
    payload: InviteMemberRequest,
    ctx: AuthContext = Depends(require_permission("org.manage_members")),
    db: Session = Depends(get_db),
):
    if payload.role_code not in SYSTEM_ROLE_CODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role: {payload.role_code}")

    already_member = (
        db.query(Membership)
        .join(User, Membership.user_id == User.id)
        .filter(
            Membership.organisation_id == ctx.organisation_id,
            User.email == payload.email,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .first()
    )
    if already_member is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person is already a member of your organisation")

    already_invited = (
        db.query(Invitation)
        .filter(
            Invitation.organisation_id == ctx.organisation_id,
            Invitation.email == payload.email,
            Invitation.status == InvitationStatus.PENDING,
        )
        .first()
    )
    if already_invited is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There's already a pending invitation for this email")

    role = _get_or_create_role(db, payload.role_code)
    invitation = Invitation(
        organisation_id=ctx.organisation_id,
        email=payload.email,
        role_id=role.id,
        token=secrets.token_urlsafe(32),
        invited_by=ctx.user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    db.flush()

    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="membership.invited",
        entity_type="invitation",
        entity_id=str(invitation.id),
        after={"email": payload.email, "role_code": payload.role_code},
    )
    db.commit()
    return _invitation_out(invitation, role.code)


@members_router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("org.manage_members")),
    db: Session = Depends(get_db),
):
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.organisation_id != ctx.organisation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a pending invitation can be revoked")
    invitation.status = InvitationStatus.REVOKED
    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="membership.invitation_revoked",
        entity_type="invitation",
        entity_id=str(invitation.id),
    )
    db.commit()


@invitations_router.get("/{token}", response_model=PublicInvitationOut)
def get_invitation(token: str, db: Session = Depends(get_db)):
    """Deliberately no auth dependency — a visitor following a shared
    invite link has no session and no org membership yet. The token is
    the entire authorization, same role the Stripe webhook signature
    plays for app/platform/router.py's webhook endpoint."""
    invitation = _resolve_pending_invitation(db, token)
    org = db.get(Organisation, invitation.organisation_id)
    role = db.get(Role, invitation.role_id)
    account_exists = db.query(User).filter(User.email == invitation.email).first() is not None
    return PublicInvitationOut(
        organisation_name=org.name if org else "",
        email=invitation.email,
        role_code=role.code if role else "",
        account_exists=account_exists,
    )


@invitations_router.post("/{token}/accept")
def accept_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    invitation = _resolve_pending_invitation(db, token)

    if current_user is not None and current_user.email != invitation.email:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You're signed in as {current_user.email}. Sign out first to accept an "
            f"invitation sent to {invitation.email}.",
        )

    existing_user = db.query(User).filter(User.email == invitation.email).first()
    if existing_user is not None:
        if current_user is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An account already exists for this email. Sign in, then open this invite link again.",
            )
        user = existing_user
    else:
        if not payload.name or not payload.password:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "name and password are required to create your account"
            )
        user = User(email=invitation.email, name=payload.name, password_hash=hash_password(payload.password))
        db.add(user)
        db.flush()

    already_member = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.organisation_id == invitation.organisation_id)
        .first()
    )
    if already_member is not None:
        already_member.status = MembershipStatus.ACTIVE
    else:
        db.add(
            Membership(
                user_id=user.id,
                organisation_id=invitation.organisation_id,
                role_id=invitation.role_id,
                status=MembershipStatus.ACTIVE,
                invited_by=invitation.invited_by,
            )
        )

    invitation.status = InvitationStatus.ACCEPTED
    record_audit_event(
        db,
        organisation_id=invitation.organisation_id,
        actor_user_id=user.id,
        action_code="membership.invitation_accepted",
        entity_type="invitation",
        entity_id=str(invitation.id),
    )
    db.commit()

    if current_user is None:
        _issue_session(db, response, user)
        db.commit()

    return {"organisation_id": str(invitation.organisation_id), "user_id": str(user.id)}
