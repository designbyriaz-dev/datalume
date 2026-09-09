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


def test_add_defect_against_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()

    resp = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={
            "category": "Windows",
            "description": "Water ingress around frame",
            "reported_date": "2026-01-10",
            "severity": "HIGH",
            "contractor": "Acme Glazing",
            "target_date": "2026-01-24",
            "estimated_cost_pence": 15000,
            "building_id": building["id"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["defect_reference"] == "DEF-000001"
    assert body["status"] == "OPEN"
    assert body["severity"] == "HIGH"
    assert body["building_id"] == building["id"]
    assert body["completion_date"] is None
    assert body["warranty_related"] is False


def test_defect_against_missing_building_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "category": "Windows",
            "description": "x",
            "reported_date": "2026-01-10",
            "building_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 404


def test_defect_status_transitions_follow_the_defined_workflow(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    defect = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={"category": "Windows", "description": "x", "reported_date": "2026-01-10"},
    ).json()
    assert defect["status"] == "OPEN"

    # OPEN -> ASSIGNED -> IN_PROGRESS -> READY_FOR_INSPECTION -> COMPLETED -> CLOSED
    for next_status in ["ASSIGNED", "IN_PROGRESS", "READY_FOR_INSPECTION"]:
        resp = client.post(
            f"/api/v1/defects/{defect['id']}/status",
            headers={"X-Organisation-Id": org_id},
            json={"status": next_status},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == next_status

    completed = client.post(
        f"/api/v1/defects/{defect['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "actual_cost_pence": 12000},
    )
    assert completed.status_code == 200
    completed_body = completed.json()
    assert completed_body["status"] == "COMPLETED"
    assert completed_body["completion_date"] is not None  # defaulted to today, not supplied
    assert completed_body["actual_cost_pence"] == 12000

    closed = client.post(
        f"/api/v1/defects/{defect['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "CLOSED"}
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def test_cannot_skip_defect_workflow_states(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    defect = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={"category": "Windows", "description": "x", "reported_date": "2026-01-10"},
    ).json()

    resp = client.post(
        f"/api/v1/defects/{defect['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED"},
    )
    assert resp.status_code == 400


def test_closed_defect_is_terminal(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    defect = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={"category": "Windows", "description": "x", "reported_date": "2026-01-10"},
    ).json()
    client.post(
        f"/api/v1/defects/{defect['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "REJECTED"}
    )
    client.post(
        f"/api/v1/defects/{defect['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "CLOSED"}
    )

    resp = client.post(
        f"/api/v1/defects/{defect['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "OPEN"}
    )
    assert resp.status_code == 400


def test_defects_intelligence_aggregates(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    prop_a = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}
    ).json()

    def add_defect(**overrides):
        payload = {
            "category": "Windows",
            "description": "x",
            "reported_date": "2026-01-01",
            "contractor": "Acme Glazing",
            "building_id": building["id"],
        }
        payload.update(overrides)
        return client.post("/api/v1/defects", headers={"X-Organisation-Id": org_id}, json=payload).json()

    d1 = add_defect(property_id=prop_a["id"], estimated_cost_pence=10000)
    add_defect(property_id=prop_a["id"], category="Windows")  # repeat category at the same property
    add_defect(category="Doors", warranty_related=True, target_date="2020-01-01")  # overdue, still OPEN

    client.post(
        f"/api/v1/defects/{d1['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "ASSIGNED"}
    )
    client.post(
        f"/api/v1/defects/{d1['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "IN_PROGRESS"}
    )
    client.post(
        f"/api/v1/defects/{d1['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "READY_FOR_INSPECTION"},
    )
    client.post(
        f"/api/v1/defects/{d1['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "actual_cost_pence": 9000, "completion_date": "2026-01-01"},
    )

    resp = client.get("/api/v1/defects/intelligence", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 3
    assert body["open_count"] == 2  # the third stays OPEN
    assert body["overdue_count"] == 1
    assert body["warranty_related_count"] == 1
    assert {"key": "Acme Glazing", "count": 3} in body["by_contractor"]
    assert {"key": "Windows", "count": 1} in body["repeat_categories"]  # 1 PROPERTY with a repeat, not 2 defects
    assert body["total_estimated_cost_pence"] == 10000
    assert body["total_actual_cost_pence"] == 9000
    assert body["average_resolution_days"] == 0.0  # completed same day as reported in this test


def test_defect_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        viewer_user = User(
            email="viewer@northstar-housing.example",
            name="Viewer Person",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(viewer_user)
        db.flush()
        viewer_role = _get_or_create_role(db, "VIEWER")
        db.add(
            Membership(
                user_id=viewer_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=viewer_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={"category": "Windows", "description": "x", "reported_date": "2026-01-10"},
    )
    assert resp.status_code == 403


def test_defect_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    defect = client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"category": "Windows", "description": "x", "reported_date": "2026-01-10"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/defects/{defect['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
