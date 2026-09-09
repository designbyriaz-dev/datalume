"""Hazards, damp & mould — architecture/04-operations-domain.md §5,
spec §49."""

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


def _property(client, org_id, address="Flat 1"):
    return client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": address}).json()


def test_report_a_hazard(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    resp = client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": "2026-01-10", "severity": "HIGH"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REPORTED"
    assert body["investigation_status"] == "PENDING"
    assert body["severity"] == "HIGH"


def test_hazard_against_missing_property_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": str(uuid.uuid4()), "hazard_type": "DAMP_AND_MOULD", "reported_date": "2026-01-10"},
    )
    assert resp.status_code == 404


def _report_hazard(client, org_id, prop_id, hazard_type="DAMP_AND_MOULD"):
    return client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop_id, "hazard_type": hazard_type, "reported_date": "2026-01-10"},
    ).json()


def test_hazard_state_machine_happy_path(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    hazard = _report_hazard(client, org_id, prop["id"])

    steps = [
        ("TRIAGED", {}),
        ("INVESTIGATING", {}),
        ("INVESTIGATED", {"investigation_status": "CONFIRMED", "findings": "Rising damp behind kitchen units"}),
        ("ACTION_IN_PROGRESS", {}),
        ("FOLLOW_UP", {}),
        ("CLOSED", {}),
    ]
    for target_status, extra in steps:
        resp = client.post(
            f"/api/v1/hazards/{hazard['id']}/status",
            headers={"X-Organisation-Id": org_id},
            json={"status": target_status, **extra},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target_status

    final = client.get(f"/api/v1/hazards/{hazard['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert final["investigation_status"] == "CONFIRMED"
    assert final["findings"] == "Rising damp behind kitchen units"


def test_hazard_cannot_skip_states(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    hazard = _report_hazard(client, org_id, prop["id"])

    resp = client.post(
        f"/api/v1/hazards/{hazard['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "INVESTIGATED"},
    )
    assert resp.status_code == 400


def test_hazard_action_lifecycle(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    hazard = _report_hazard(client, org_id, prop["id"])

    action = client.post(
        f"/api/v1/hazards/{hazard['id']}/actions",
        headers={"X-Organisation-Id": org_id},
        json={"description": "Treat mould, install extractor fan", "deadline": "2026-02-10"},
    )
    assert action.status_code == 201
    action_body = action.json()
    assert action_body["status"] == "OPEN"

    completed = client.post(
        f"/api/v1/hazard-actions/{action_body['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "COMPLETED", "completed_date": "2026-02-05"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["completed_date"] == "2026-02-05"

    listed = client.get(f"/api/v1/hazards/{hazard['id']}/actions", headers={"X-Organisation-Id": org_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_repeat_hazard_signal_triggers_at_threshold(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    # Default threshold is 2 within 24 months.
    below = client.get(
        "/api/v1/properties/{}/repeat-hazards".format(prop["id"]),
        headers={"X-Organisation-Id": org_id},
        params={"hazard_type": "DAMP_AND_MOULD"},
    )
    assert below.status_code == 200
    assert below.json() is None

    _report_hazard(client, org_id, prop["id"])
    _report_hazard(client, org_id, prop["id"])

    resp = client.get(
        "/api/v1/properties/{}/repeat-hazards".format(prop["id"]),
        headers={"X-Organisation-Id": org_id},
        params={"hazard_type": "DAMP_AND_MOULD"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["hazard_count"] == 2
    assert body["threshold"] == 2


def test_repeat_hazard_signal_does_not_mix_hazard_types(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    _report_hazard(client, org_id, prop["id"], hazard_type="DAMP_AND_MOULD")
    _report_hazard(client, org_id, prop["id"], hazard_type="EXCESS_COLD")

    resp = client.get(
        "/api/v1/properties/{}/repeat-hazards".format(prop["id"]),
        headers={"X-Organisation-Id": org_id},
        params={"hazard_type": "DAMP_AND_MOULD"},
    )
    assert resp.json() is None


def test_raising_hazard_rule_config_threshold_silences_signal(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    _report_hazard(client, org_id, prop["id"])
    _report_hazard(client, org_id, prop["id"])

    triggered = client.get(
        "/api/v1/properties/{}/repeat-hazards".format(prop["id"]),
        headers={"X-Organisation-Id": org_id},
        params={"hazard_type": "DAMP_AND_MOULD"},
    ).json()
    assert triggered is not None

    client.patch(
        "/api/v1/hazard-rule-configs/REPEAT_HAZARDS_PER_PROPERTY",
        headers={"X-Organisation-Id": org_id},
        json={"threshold": 5},
    )

    silenced = client.get(
        "/api/v1/properties/{}/repeat-hazards".format(prop["id"]),
        headers={"X-Organisation-Id": org_id},
        params={"hazard_type": "DAMP_AND_MOULD"},
    ).json()
    assert silenced is None


def test_hazard_write_requires_operations_compliance_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-housing.example",
            name="Property Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "PROPERTY_MANAGER")
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
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": "2026-01-10"},
    )
    assert resp.status_code == 403


def test_hazard_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop = _property(client, org_a)
    hazard = _report_hazard(client, org_a, prop["id"])

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(f"/api/v1/hazards/{hazard['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]})
    assert resp.status_code == 404
