import uuid
from datetime import datetime, timedelta, timezone

import app.core.db as db_module
from app.auth.models import Invitation, InvitationStatus, Membership, MembershipStatus, User
from app.auth.router import _get_or_create_role
from app.core.security import hash_password


def _signup_payload(**overrides):
    payload = {
        "name": "Jamie Ward",
        "email": "jamie@northstar-housing.example",
        "password": "correct-horse-battery",
        "organisation_name": "Northstar Housing",
        "organisation_type": "HOUSING_ASSOCIATION",
        "goals": [],
    }
    payload.update(overrides)
    return payload


def _signup(client, **overrides):
    return client.post("/api/v1/auth/signup", json=_signup_payload(**overrides)).json()


def test_owner_can_invite_and_list(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "new.colleague@northstar-housing.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": org_id},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new.colleague@northstar-housing.example"
    assert body["role_code"] == "VIEWER"
    assert body["status"] == "PENDING"
    assert "token=" in body["invite_url"]

    listed = client.get("/api/v1/organisations/invitations", headers={"X-Organisation-Id": org_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    members = client.get("/api/v1/organisations/members", headers={"X-Organisation-Id": org_id})
    assert members.status_code == 200
    assert len(members.json()) == 1
    assert members.json()[0]["role_code"] == "OWNER"


def test_invite_rejects_unknown_role(client):
    signup = _signup(client)
    resp = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "x@example.com", "role_code": "NOT_A_REAL_ROLE"},
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 400


def test_invite_conflicts_on_duplicate_pending(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]
    payload = {"email": "dup@northstar-housing.example", "role_code": "VIEWER"}
    first = client.post("/api/v1/organisations/invitations", json=payload, headers={"X-Organisation-Id": org_id})
    assert first.status_code == 201
    second = client.post("/api/v1/organisations/invitations", json=payload, headers={"X-Organisation-Id": org_id})
    assert second.status_code == 409


def test_invite_conflicts_on_existing_member(client):
    signup = _signup(client)
    resp = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "jamie@northstar-housing.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 409


def test_viewer_cannot_invite(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    viewer = User(email="viewer@northstar-housing.example", name="Viewer", password_hash=hash_password("correct-horse-battery"))
    db.add(viewer)
    db.flush()
    viewer_role = _get_or_create_role(db, "VIEWER")
    db.add(Membership(user_id=viewer.id, organisation_id=uuid.UUID(org_id), role_id=viewer_role.id, status=MembershipStatus.ACTIVE))
    db.commit()
    db.close()

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "viewer@northstar-housing.example", "password": "correct-horse-battery"})

    resp = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "someone@northstar-housing.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": org_id},
    )
    assert resp.status_code == 403


def test_revoke_invitation(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]
    created = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "revoke-me@northstar-housing.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": org_id},
    ).json()

    revoke = client.delete(f"/api/v1/organisations/invitations/{created['id']}", headers={"X-Organisation-Id": org_id})
    assert revoke.status_code == 204

    listed = client.get("/api/v1/organisations/invitations", headers={"X-Organisation-Id": org_id})
    assert listed.json() == []

    token = created["invite_url"].split("token=")[1]
    lookup = client.get(f"/api/v1/invitations/{token}")
    assert lookup.status_code == 410


def test_accept_invitation_creates_account_and_logs_in(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]
    invite = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "newperson@northstar-housing.example", "role_code": "MANAGER"},
        headers={"X-Organisation-Id": org_id},
    ).json()
    token = invite["invite_url"].split("token=")[1]

    client.cookies.clear()

    info = client.get(f"/api/v1/invitations/{token}")
    assert info.status_code == 200
    assert info.json() == {
        "organisation_name": "Northstar Housing",
        "email": "newperson@northstar-housing.example",
        "role_code": "MANAGER",
        "account_exists": False,
    }

    accept = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"name": "New Person", "password": "another-correct-password"},
    )
    assert accept.status_code == 200
    assert accept.json()["organisation_id"] == org_id

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "newperson@northstar-housing.example"
    assert me.json()["memberships"][0]["role_code"] == "MANAGER"


def test_accept_invitation_for_existing_account_requires_sign_in(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]

    second_org = _signup(
        client,
        name="Alex Carter",
        email="alex@othercompany.example",
        organisation_name="Other Company",
    )

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"})

    invite = client.post(
        "/api/v1/organisations/invitations",
        json={"email": "alex@othercompany.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": org_id},
    ).json()
    token = invite["invite_url"].split("token=")[1]

    client.cookies.clear()

    info = client.get(f"/api/v1/invitations/{token}")
    assert info.json()["account_exists"] is True

    denied = client.post(f"/api/v1/invitations/{token}/accept", json={})
    assert denied.status_code == 409

    client.post("/api/v1/auth/login", json={"email": "alex@othercompany.example", "password": "correct-horse-battery"})
    accept = client.post(f"/api/v1/invitations/{token}/accept", json={})
    assert accept.status_code == 200

    me = client.get("/api/v1/auth/me")
    assert len(me.json()["memberships"]) == 2


def test_expired_invitation_rejected(client):
    signup = _signup(client)
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    role = _get_or_create_role(db, "VIEWER")
    invitation = Invitation(
        organisation_id=uuid.UUID(org_id),
        email="late@northstar-housing.example",
        role_id=role.id,
        token="expired-token-value",
        invited_by=uuid.UUID(signup["user_id"]),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(invitation)
    db.commit()
    db.close()

    resp = client.get("/api/v1/invitations/expired-token-value")
    assert resp.status_code == 410


def test_invitations_are_scoped_to_organisation(client):
    org_a = _signup(client)
    client.post("/api/v1/auth/logout")
    org_b = _signup(
        client,
        name="Sam Lee",
        email="sam@commercial-co.example",
        organisation_name="Commercial Co",
    )

    client.post(
        "/api/v1/organisations/invitations",
        json={"email": "invitee@commercial-co.example", "role_code": "VIEWER"},
        headers={"X-Organisation-Id": org_b["organisation_id"]},
    )

    listed_for_a = client.get("/api/v1/organisations/invitations", headers={"X-Organisation-Id": org_a["organisation_id"]})
    assert listed_for_a.status_code == 403  # sam isn't a member of org_a at all
