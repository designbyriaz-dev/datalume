import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.models import Membership, MembershipStatus, Role, Session as SessionModel, User
from app.auth.schemas import LoginRequest, MeResponse, MembershipSummary, SignupRequest
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_password, new_session_token, verify_password
from app.core.tenancy import hash_session_token, get_current_user, redis_client
from app.organisations.models import Organisation, Workspace
from app.platform.audit import record_audit_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


def _slugify(name: str) -> str:
    base = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    return base or str(uuid.uuid4())[:8]


def _get_or_create_role(db: Session, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code, Role.organisation_id.is_(None)).first()
    if role is None:
        role = Role(code=code, name=code.replace("_", " ").title(), organisation_id=None)
        db.add(role)
        db.flush()
    return role


def _issue_session(db: Session, response: Response, user: User, request_ip: str | None = None) -> None:
    token = new_session_token()
    redis_client.set(f"session:{hash_session_token(token)}", str(user.id), ex=settings.session_ttl_seconds)
    db.add(SessionModel(user_id=user.id, token_hash=hash_session_token(token), ip_address=request_ip))
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.environment != "local",
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=payload.email, name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()

    slug_base = _slugify(payload.organisation_name)
    slug = slug_base
    suffix = 1
    while db.query(Organisation).filter(Organisation.slug == slug).first():
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    org = Organisation(
        name=payload.organisation_name,
        slug=slug,
        organisation_type=payload.organisation_type,
        goals=payload.goals,
    )
    db.add(org)
    db.flush()

    db.add(Workspace(organisation_id=org.id, name="Default Workspace", workspace_type="DEFAULT"))

    owner_role = _get_or_create_role(db, "OWNER")
    db.add(
        Membership(
            user_id=user.id,
            organisation_id=org.id,
            role_id=owner_role.id,
            status=MembershipStatus.ACTIVE,
        )
    )

    record_audit_event(
        db,
        organisation_id=org.id,
        actor_user_id=user.id,
        action_code="organisation.created_via_signup",
        entity_type="organisation",
        entity_id=str(org.id),
        after={"name": org.name, "organisation_type": org.organisation_type.value},
    )

    db.commit()
    _issue_session(db, response, user)
    db.commit()
    return {"organisation_id": str(org.id), "organisation_slug": org.slug, "user_id": str(user.id)}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    _issue_session(db, response, user)
    db.commit()
    return {"user_id": str(user.id)}


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = (
        db.query(Membership, Organisation, Role)
        .join(Organisation, Membership.organisation_id == Organisation.id)
        .join(Role, Membership.role_id == Role.id)
        .filter(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
        .all()
    )
    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        memberships=[
            MembershipSummary(organisation_id=org.id, organisation_name=org.name, role_code=role.code)
            for _m, org, role in memberships
        ],
    )
