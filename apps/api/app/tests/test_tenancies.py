"""Tenancies — architecture/05-commercial-domain.md §1."""

import uuid
from datetime import date, timedelta


def _signup_payload(**overrides):
    payload = {
        "name": "Jamie Ward",
        "email": "jamie@northstar-commercial.example",
        "password": "correct-horse-battery",
        "organisation_name": "Northstar Commercial",
        "organisation_type": "COMMERCIAL_LANDLORD",
        "goals": [],
    }
    payload.update(overrides)
    return payload


def _property(client, org_id, address="Unit 1"):
    return client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": address}).json()


def _tenant(client, org_id, name="Acme Retail Ltd"):
    return client.post("/api/v1/tenants", headers={"X-Organisation-Id": org_id}, json={"name": name}).json()


def test_create_tenant(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/tenants",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Acme Retail Ltd", "contact_details": {"email": "ops@acme.example"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Acme Retail Ltd"
    assert body["contact_details"] == {"email": "ops@acme.example"}


def test_create_lease(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    tenant = _tenant(client, org_id)

    resp = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lease_reference"].startswith("LSE-")
    assert body["lease_status"] == "DRAFT"
    assert body["occupancy_status"] == "OCCUPIED"
    assert body["contractual_rent_pence"] == 250000


def test_lease_against_missing_property_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    tenant = _tenant(client, org_id)

    resp = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": str(uuid.uuid4()),
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    )
    assert resp.status_code == 404


def test_lease_against_missing_tenant_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    resp = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": str(uuid.uuid4()),
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    )
    assert resp.status_code == 404


def _create_lease(client, org_id, prop, tenant):
    return client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    ).json()


def test_lease_status_transitions(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _create_lease(client, org_id, _property(client, org_id), _tenant(client, org_id))

    resp = client.post(
        f"/api/v1/leases/{lease['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "ACTIVE"}
    )
    assert resp.status_code == 200
    assert resp.json()["lease_status"] == "ACTIVE"

    resp2 = client.post(
        f"/api/v1/leases/{lease['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "EXPIRED"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["lease_status"] == "EXPIRED"

    # Terminal — no further transitions allowed.
    resp3 = client.post(
        f"/api/v1/leases/{lease['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "ACTIVE"}
    )
    assert resp3.status_code == 400


def test_lease_cannot_skip_draft_to_expired(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _create_lease(client, org_id, _property(client, org_id), _tenant(client, org_id))

    resp = client.post(
        f"/api/v1/leases/{lease['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "EXPIRED"}
    )
    assert resp.status_code == 400


def test_occupancy_status_freely_settable(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _create_lease(client, org_id, _property(client, org_id), _tenant(client, org_id))

    resp = client.post(
        f"/api/v1/leases/{lease['id']}/occupancy",
        headers={"X-Organisation-Id": org_id},
        json={"occupancy_status": "NOTICE_GIVEN"},
    )
    assert resp.status_code == 200
    assert resp.json()["occupancy_status"] == "NOTICE_GIVEN"

    # Can go back to OCCUPIED — no directional restriction, unlike lease_status.
    resp2 = client.post(
        f"/api/v1/leases/{lease['id']}/occupancy",
        headers={"X-Organisation-Id": org_id},
        json={"occupancy_status": "OCCUPIED"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["occupancy_status"] == "OCCUPIED"


def test_list_leases_filters(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop_a = _property(client, org_id, "Unit A")
    prop_b = _property(client, org_id, "Unit B")
    tenant = _tenant(client, org_id)
    lease_a = _create_lease(client, org_id, prop_a, tenant)
    _create_lease(client, org_id, prop_b, tenant)

    resp = client.get("/api/v1/leases", headers={"X-Organisation-Id": org_id}, params={"property_id": prop_a["id"]})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == lease_a["id"]

    resp2 = client.get("/api/v1/leases", headers={"X-Organisation-Id": org_id}, params={"lease_status": "DRAFT"})
    assert len(resp2.json()) == 2


def test_lease_write_requires_commercial_write_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    tenant = _tenant(client, org_id)

    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-commercial.example",
            name="Repairs Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "REPAIRS_MANAGER")
        db.add(
            Membership(
                user_id=manager_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=manager_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "manager@northstar-commercial.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    )
    assert resp.status_code == 403


def test_lease_manager_can_write(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    tenant = _tenant(client, org_id)

    db = db_module.SessionLocal()
    try:
        lease_manager_user = User(
            email="lease-manager@northstar-commercial.example",
            name="Lease Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(lease_manager_user)
        db.flush()
        role = _get_or_create_role(db, "LEASE_MANAGER")
        db.add(
            Membership(
                user_id=lease_manager_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "lease-manager@northstar-commercial.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    )
    assert resp.status_code == 201


def test_lease_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    lease = _create_lease(client, org_a, _property(client, org_a), _tenant(client, org_a))

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(f"/api/v1/leases/{lease['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]})
    assert resp.status_code == 404
