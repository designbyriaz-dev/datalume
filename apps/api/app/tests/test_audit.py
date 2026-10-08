import uuid


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


def test_audit_log_lists_an_event_recorded_by_another_domain(client):
    """GET /api/v1/audit never writes an AuditEvent itself — it only reads
    back what app/development/service.py's create_property already
    recorded via record_audit_event. Proves the read side against a real
    write from another module, not a hand-inserted row."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 Audit Way"}
    ).json()

    resp = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "entity_id": prop["id"]},
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    event = events[0]
    assert event["action_code"] == "property.created"
    assert event["entity_type"] == "property"
    assert event["entity_id"] == prop["id"]
    assert event["after"]["property_reference"] == prop["property_reference"]
    assert event["actor_name"] == "Jamie Ward"
    assert event["before"] is None


def test_audit_log_requires_owner_or_admin_permission(client):
    """OWNER/ADMIN only, via the wildcard permission — platform.audit is
    deliberately not granted to any other role (see app/platform/router.py
    for why: audit events can reveal other users' edits across every
    domain, which is more sensitive than any one domain's own data)."""
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-housing.example",
            name="Manager Person",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "MANAGER")
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
        json={"email": "manager@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.get("/api/v1/audit", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 403


def test_audit_log_is_tenant_isolated(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop_a = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_a}, json={"address": "Org A's property"}
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()
    org_b = signup_b["organisation_id"]

    resp = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_b},
        params={"entity_type": "property", "entity_id": prop_a["id"]},
    )
    assert resp.status_code == 200
    assert resp.json() == []

    # Not just the filtered-out case — org B's unfiltered audit log must
    # never contain org A's event either.
    resp_unfiltered = client.get("/api/v1/audit", headers={"X-Organisation-Id": org_b})
    assert prop_a["id"] not in [e["entity_id"] for e in resp_unfiltered.json()]


def test_audit_log_pagination(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    created_ids = []
    for i in range(5):
        prop = client.post(
            "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": f"Flat {i}"}
        ).json()
        created_ids.append(prop["id"])

    page1 = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "limit": 2, "offset": 0},
    ).json()
    page2 = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "limit": 2, "offset": 2},
    ).json()
    assert len(page1) == 2
    assert len(page2) == 2
    assert {e["id"] for e in page1}.isdisjoint({e["id"] for e in page2})

    all_events = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "limit": 100, "offset": 0},
    ).json()
    assert len(all_events) == 5
    assert {e["entity_id"] for e in all_events} == set(created_ids)


def test_audit_log_filters_by_date_range(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 Audit Way"}
    ).json()
    params = {"entity_type": "property", "entity_id": prop["id"]}

    future = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={**params, "created_from": "2999-01-01T00:00:00"},
    ).json()
    assert future == []

    past = client.get(
        "/api/v1/audit",
        headers={"X-Organisation-Id": org_id},
        params={**params, "created_from": "2000-01-01T00:00:00", "created_to": "2999-01-01T00:00:00"},
    ).json()
    assert len(past) == 1
