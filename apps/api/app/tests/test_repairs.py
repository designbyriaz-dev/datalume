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


def _boiler_type_id(client, org_id):
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    return next(t["id"] for t in types if t["code"] == "BOILERS")


def test_add_repair_against_a_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    resp = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "category": "Plumbing",
            "description": "Leaking tap",
            "reported_date": "2026-01-01",
            "priority": "URGENT",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["repair_reference"] == "REP-000001"
    assert body["status"] == "REPORTED"
    assert body["priority"] == "URGENT"
    assert body["is_emergency"] is False


def test_emergency_priority_sets_is_emergency(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    resp = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "category": "Gas",
            "description": "Gas leak reported",
            "reported_date": "2026-01-01",
            "priority": "EMERGENCY",
        },
    )
    assert resp.json()["is_emergency"] is True


def test_repair_against_missing_property_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "property_id": str(uuid.uuid4()),
            "category": "Plumbing",
            "description": "x",
            "reported_date": "2026-01-01",
        },
    )
    assert resp.status_code == 404


def test_repair_status_workflow(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    repair = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": "2026-01-01"},
    ).json()

    for next_status in ["SCHEDULED", "IN_PROGRESS"]:
        resp = client.post(
            f"/api/v1/repairs/{repair['id']}/status",
            headers={"X-Organisation-Id": org_id},
            json={"status": next_status},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == next_status

    completed = client.post(
        f"/api/v1/repairs/{repair['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "cost_pence": 8500},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "COMPLETED"
    assert body["completed_date"] is not None
    assert body["cost_pence"] == 8500


def test_cannot_skip_repair_workflow_states(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    repair = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": "2026-01-01"},
    ).json()

    resp = client.post(
        f"/api/v1/repairs/{repair['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED"},
    )
    assert resp.status_code == 400


def test_repeat_repairs_for_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    # Below threshold (default 3) — no signal yet.
    for i in range(2):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={
                "property_id": prop["id"],
                "category": "Damp",
                "description": f"Damp issue {i}",
                "reported_date": "2026-01-01",
            },
        )
    below = client.get(
        f"/api/v1/properties/{prop['id']}/repeat-repairs", headers={"X-Organisation-Id": org_id}
    ).json()
    assert below is None

    client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "category": "Damp",
            "description": "Damp issue 3",
            "reported_date": "2026-01-01",
        },
    )
    resp = client.get(f"/api/v1/properties/{prop['id']}/repeat-repairs", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["property_id"] == prop["id"]
    assert body["repair_count"] == 3
    assert body["window_months"] == 12
    assert body["threshold"] == 3
    assert len(body["repair_ids"]) == 3


def test_repeat_repairs_excludes_cancelled_and_old_repairs(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    # One old repair (outside the 12-month window), one cancelled, one live — nowhere near threshold 3.
    old = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Damp", "description": "x", "reported_date": "2020-01-01"},
    ).json()
    cancelled = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Damp", "description": "x", "reported_date": "2026-01-01"},
    ).json()
    client.post(
        f"/api/v1/repairs/{cancelled['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "CANCELLED"}
    )
    client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Damp", "description": "x", "reported_date": "2026-01-01"},
    )

    resp = client.get(f"/api/v1/properties/{prop['id']}/repeat-repairs", headers={"X-Organisation-Id": org_id})
    assert resp.json() is None


def test_repeat_failures_for_component(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    boiler_type_id = _boiler_type_id(client, org_id)
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop["id"]},
    ).json()

    for i in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={
                "property_id": prop["id"],
                "component_id": component["id"],
                "category": "Heating",
                "description": f"Boiler fault {i}",
                "reported_date": "2026-01-01",
            },
        )

    resp = client.get(f"/api/v1/components/{component['id']}/repeat-failures", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["component_id"] == component["id"]
    assert body["repair_count"] == 3
    assert body["window_months"] == 18


def test_component_model_trend_requires_minimum_installed_base(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)

    # Only 2 installed units of this exact model — below the default
    # min_installed_base of 10, so no signal even if both have failed.
    components = []
    for _ in range(2):
        prop = client.post(
            "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat X"}
        ).json()
        c = client.post(
            "/api/v1/components",
            headers={"X-Organisation-Id": org_id},
            json={
                "component_type_id": boiler_type_id,
                "property_id": prop["id"],
                "manufacturer": "Worcester Bosch",
                "model": "Greenstar 8000",
            },
        ).json()
        components.append(c)
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={
                "property_id": prop["id"],
                "component_id": c["id"],
                "category": "Heating",
                "description": "Fault",
                "reported_date": "2026-01-01",
            },
        )

    resp = client.get(
        "/api/v1/repairs/model-trend",
        headers={"X-Organisation-Id": org_id},
        params={"component_type_id": boiler_type_id, "manufacturer": "Worcester Bosch", "model": "Greenstar 8000"},
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_component_model_trend_triggers_above_min_base_and_ratio(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)

    # Lower the bar so this test doesn't need to create 10+ components.
    client.patch(
        "/api/v1/repair-rule-configs/COMPONENT_MODEL_TREND",
        headers={"X-Organisation-Id": org_id},
        json={"min_installed_base": 2, "threshold_ratio": 0.3},
    )

    failed_component_id = None
    for i in range(3):
        prop = client.post(
            "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": f"Flat {i}"}
        ).json()
        c = client.post(
            "/api/v1/components",
            headers={"X-Organisation-Id": org_id},
            json={
                "component_type_id": boiler_type_id,
                "property_id": prop["id"],
                "manufacturer": "Worcester Bosch",
                "model": "Greenstar 8000",
            },
        ).json()
        if i == 0:
            failed_component_id = c["id"]
            client.post(
                "/api/v1/repairs",
                headers={"X-Organisation-Id": org_id},
                json={
                    "property_id": prop["id"],
                    "component_id": c["id"],
                    "category": "Heating",
                    "description": "Fault",
                    "reported_date": "2026-01-01",
                },
            )

    resp = client.get(
        "/api/v1/repairs/model-trend",
        headers={"X-Organisation-Id": org_id},
        params={"component_type_id": boiler_type_id, "manufacturer": "Worcester Bosch", "model": "Greenstar 8000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["installed_count"] == 3
    assert body["failed_count"] == 1
    assert body["component_ids"] == [failed_component_id]


def test_repairs_intelligence_aggregates(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    r1 = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "category": "Plumbing",
            "description": "x",
            "reported_date": "2026-01-01",
            "contractor": "Acme Plumbing",
            "priority": "EMERGENCY",
        },
    ).json()
    client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "category": "Plumbing",
            "description": "y",
            "reported_date": "2026-01-01",
            "contractor": "Acme Plumbing",
        },
    )
    client.post(
        f"/api/v1/repairs/{r1['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "SCHEDULED"}
    )
    client.post(
        f"/api/v1/repairs/{r1['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "IN_PROGRESS"}
    )
    client.post(
        f"/api/v1/repairs/{r1['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "cost_pence": 5000, "completed_date": "2026-01-01"},
    )

    resp = client.get("/api/v1/repairs/intelligence", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    assert body["open_count"] == 1
    assert body["completed_count"] == 1
    assert body["emergency_count"] == 1
    assert {"key": "Acme Plumbing", "count": 2} in body["by_contractor"]
    assert body["total_cost_pence"] == 5000
    assert body["average_completion_days"] == 0.0


def test_repair_rule_configs_default_and_update(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.get("/api/v1/repair-rule-configs", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    configs = {c["rule_code"]: c for c in resp.json()}
    assert configs["REPEAT_REPAIRS_PER_PROPERTY"]["threshold"] == 3
    assert configs["COMPONENT_MODEL_TREND"]["threshold_ratio"] == 0.15

    update = client.patch(
        "/api/v1/repair-rule-configs/REPEAT_REPAIRS_PER_PROPERTY",
        headers={"X-Organisation-Id": org_id},
        json={"threshold": 5},
    )
    assert update.status_code == 200
    assert update.json()["threshold"] == 5

    update_unknown = client.patch(
        "/api/v1/repair-rule-configs/NOT_A_REAL_RULE", headers={"X-Organisation-Id": org_id}, json={"threshold": 1}
    )
    assert update_unknown.status_code == 404


def test_repair_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

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
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": "2026-01-01"},
    )
    assert resp.status_code == 403


def test_repair_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"address": "Flat 1"}
    ).json()
    repair = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": "2026-01-01"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(f"/api/v1/repairs/{repair['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]})
    assert resp.status_code == 404
