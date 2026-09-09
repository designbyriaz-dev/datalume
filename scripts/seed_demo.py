"""Seed the fictional demo organisation Northstar Housing.

Foundation-only for now (Sprint 1): creates the organisation, its default
workspace, and an owner login you can sign in with locally. The full
demo dataset (Riverside Gardens development, ~12,480 operational
properties, components, repairs, compliance, etc. — architecture/10
§ "Demo — Northstar Housing") gets built out incrementally as each
domain module lands, per the sprint order in
architecture/10-roadmap-and-acceptance.md. Re-running this script is
idempotent — it upserts by slug/email rather than duplicating.

All data created here is fictional/synthetic, per spec §70.

Usage (from apps/api, with the venv active and DATABASE_URL pointed at
a running Postgres):

    python ../../scripts/seed_demo.py
"""

from app.auth.models import Membership, MembershipStatus, Role
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.organisations.models import Organisation, OrganisationType, Workspace
from app.auth.models import User

DEMO_OWNER_EMAIL = "demo-owner@northstar-housing.example"
DEMO_OWNER_PASSWORD = "northstar-demo-2026"  # local/demo only — never used outside seeded environments


def get_or_create_role(db, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code, Role.organisation_id.is_(None)).first()
    if role is None:
        role = Role(code=code, name=code.replace("_", " ").title(), organisation_id=None)
        db.add(role)
        db.flush()
    return role


def main() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organisation).filter(Organisation.slug == "northstar-housing").first()
        if org is None:
            org = Organisation(
                name="Northstar Housing (fictional demo)",
                slug="northstar-housing",
                organisation_type=OrganisationType.HOUSING_ASSOCIATION,
                goals=["understand_portfolio", "monitor_compliance", "manage_new_developments"],
            )
            db.add(org)
            db.flush()
            db.add(Workspace(organisation_id=org.id, name="Default Workspace", workspace_type="DEFAULT"))
            print(f"Created organisation {org.name} ({org.slug})")
        else:
            print(f"Organisation {org.slug} already exists, reusing")

        user = db.query(User).filter(User.email == DEMO_OWNER_EMAIL).first()
        if user is None:
            user = User(
                email=DEMO_OWNER_EMAIL,
                name="Demo Owner",
                password_hash=hash_password(DEMO_OWNER_PASSWORD),
            )
            db.add(user)
            db.flush()
            print(f"Created demo login {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")
        else:
            print(f"User {DEMO_OWNER_EMAIL} already exists, reusing")

        existing_membership = (
            db.query(Membership)
            .filter(Membership.user_id == user.id, Membership.organisation_id == org.id)
            .first()
        )
        if existing_membership is None:
            owner_role = get_or_create_role(db, "OWNER")
            db.add(
                Membership(
                    user_id=user.id,
                    organisation_id=org.id,
                    role_id=owner_role.id,
                    status=MembershipStatus.ACTIVE,
                )
            )
            print("Granted OWNER membership")

        db.commit()
        print("\nDone. Sign in at the web app with:")
        print(f"  email:    {DEMO_OWNER_EMAIL}")
        print(f"  password: {DEMO_OWNER_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
