"""Compliance Operations — Sprint 16: Inspection and ComplianceAction,
the INSPECTION -> EVIDENCE -> ACTION -> DEADLINE links added to Sprint
15's FRAMEWORK -> DOMAIN -> REQUIREMENT -> APPLICABILITY chain."""

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


def _gas_safety_domain_id(client, org_id):
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    return next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")


def _setup_requirement_and_building(client, org_id):
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    return requirement, building


def test_record_inspection_against_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)

    resp = client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "Gas Safe Engineer Ltd",
            "inspection_date": "2026-01-15",
            "result": "SATISFACTORY",
            "next_due_date": "2027-01-15",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["result"] == "SATISFACTORY"
    assert body["next_due_date"] == "2027-01-15"


def test_inspection_against_missing_requirement_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()

    resp = client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": str(uuid.uuid4()),
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "x",
            "inspection_date": "2026-01-15",
            "result": "SATISFACTORY",
        },
    )
    assert resp.status_code == 404


def test_inspection_against_unsupported_entity_type_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, _ = _setup_requirement_and_building(client, org_id)

    resp = client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "development",
            "entity_id": str(uuid.uuid4()),
            "inspector": "x",
            "inspection_date": "2026-01-15",
            "result": "SATISFACTORY",
        },
    )
    assert resp.status_code == 400


def test_list_inspections_filters_by_entity(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)
    other_building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}
    ).json()

    for target in (building, other_building):
        client.post(
            "/api/v1/compliance/inspections",
            headers={"X-Organisation-Id": org_id},
            json={
                "requirement_id": requirement["id"],
                "entity_type": "building",
                "entity_id": target["id"],
                "inspector": "x",
                "inspection_date": "2026-01-15",
                "result": "SATISFACTORY",
            },
        )

    resp = client.get(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "building", "entity_id": building["id"]},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["entity_id"] == building["id"]


def test_raise_compliance_action_from_an_inspection(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)
    inspection = client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "x",
            "inspection_date": "2026-01-15",
            "result": "UNSATISFACTORY",
        },
    ).json()

    resp = client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "Replace faulty flue seal",
            "deadline": "2026-02-15",
            "inspection_id": inspection["id"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "OPEN"
    assert body["inspection_id"] == inspection["id"]


def test_compliance_action_status_transitions(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)
    action = client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "x",
            "deadline": "2026-02-15",
        },
    ).json()

    resp = client.post(
        f"/api/v1/compliance/actions/{action['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "completed_date": "2026-02-10"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["completed_date"] == "2026-02-10"

    # Terminal — cannot transition again.
    resp2 = client.post(
        f"/api/v1/compliance/actions/{action['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "CANCELLED"},
    )
    assert resp2.status_code == 400


def test_list_compliance_actions_filters_by_status(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)
    open_action = client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "open one",
            "deadline": "2026-02-15",
        },
    ).json()
    completed_action = client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "completed one",
            "deadline": "2026-02-15",
        },
    ).json()
    client.post(
        f"/api/v1/compliance/actions/{completed_action['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED"},
    )

    resp = client.get(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        params={"action_status": "OPEN"},
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert ids == {open_action["id"]}


def test_compliance_operations_write_requires_operations_compliance_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    requirement, building = _setup_requirement_and_building(client, org_id)

    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-housing.example",
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
        json={"email": "manager@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "x",
            "inspection_date": "2026-01-15",
            "result": "SATISFACTORY",
        },
    )
    assert resp.status_code == 403
