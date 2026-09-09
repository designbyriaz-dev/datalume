"""Compliance status engine — architecture/04-operations-domain.md §4,
spec §47: deterministic, computed at read time, never LLM-set. Each
test isolates one branch of the status_engine.py pseudocode."""

import uuid
from datetime import date, timedelta


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


def _setup(client, hard_deadline=True):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={
            "domain_id": domain_id,
            "code": "GAS-001",
            "title": "Annual gas safety check",
            "effective_date": "2024-01-01",
            "hard_deadline": hard_deadline,
        },
    ).json()
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    return org_id, requirement, building


def _status(client, org_id, requirement_id, entity_id, entity_type="building"):
    resp = client.get(
        "/api/v1/compliance/status",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": entity_type, "entity_id": entity_id, "requirement_id": requirement_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_not_applicable_with_no_applicability_row(client):
    org_id, requirement, building = _setup(client)
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "NOT_APPLICABLE"


def test_unknown_when_recently_applicable_with_no_inspection(client):
    org_id, requirement, building = _setup(client)
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": date.today().isoformat(),
        },
    )
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "UNKNOWN"


def test_missing_evidence_once_grace_period_elapses_with_no_inspection(client):
    org_id, requirement, building = _setup(client)
    old_date = (date.today() - timedelta(days=200)).isoformat()
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": old_date,
        },
    )
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "MISSING_EVIDENCE"


def _make_applicable_and_inspected(client, org_id, requirement, building, *, next_due_date, result="SATISFACTORY"):
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": "2024-01-01",
        },
    )
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2026-01-01",
            "result": result,
            "next_due_date": next_due_date,
        },
    )


def test_current_when_satisfactory_and_far_from_due(client):
    org_id, requirement, building = _setup(client)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=far_future)
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "CURRENT"


def test_due_soon_within_threshold(client):
    org_id, requirement, building = _setup(client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=soon)
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "DUE_SOON"
    assert body["days_to_due"] == 10


def test_needs_review_when_last_result_not_satisfactory_and_far_from_due(client):
    org_id, requirement, building = _setup(client)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=far_future, result="ADVISORY")
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "NEEDS_REVIEW"


def test_overdue_when_hard_deadline_and_next_due_date_passed(client):
    org_id, requirement, building = _setup(client, hard_deadline=True)
    past = (date.today() - timedelta(days=5)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=past)
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "OVERDUE"
    assert body["days_to_due"] == -5


def test_expired_when_soft_deadline_and_next_due_date_passed(client):
    org_id, requirement, building = _setup(client, hard_deadline=False)
    past = (date.today() - timedelta(days=5)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=past)
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "EXPIRED"


def test_open_action_when_action_open_and_not_overdue(client):
    org_id, requirement, building = _setup(client)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=far_future)
    action_deadline = (date.today() + timedelta(days=10)).isoformat()
    client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "Replace flue seal",
            "deadline": action_deadline,
        },
    )
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "OPEN_ACTION"
    assert body["open_action"] is not None


def test_overdue_action_when_action_open_and_past_its_own_deadline(client):
    org_id, requirement, building = _setup(client)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=far_future)
    action_deadline = (date.today() - timedelta(days=3)).isoformat()
    client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "description": "Replace flue seal",
            "deadline": action_deadline,
        },
    )
    body = _status(client, org_id, requirement["id"], building["id"])
    assert body["status"] == "OVERDUE_ACTION"


def test_bulk_statuses_for_entity(client):
    org_id, requirement, building = _setup(client)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=far_future)
    resp = client.get(
        "/api/v1/compliance/statuses",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "building", "entity_id": building["id"]},
    )
    assert resp.status_code == 200
    statuses = resp.json()
    assert len(statuses) == 1
    assert statuses[0]["status"] == "CURRENT"
    assert statuses[0]["requirement_id"] == requirement["id"]


def test_raising_due_soon_threshold_turns_due_soon_into_current(client):
    org_id, requirement, building = _setup(client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    _make_applicable_and_inspected(client, org_id, requirement, building, next_due_date=soon)
    triggered = _status(client, org_id, requirement["id"], building["id"])
    assert triggered["status"] == "DUE_SOON"

    resp = client.patch(
        "/api/v1/compliance/status-config", headers={"X-Organisation-Id": org_id}, json={"due_soon_days": 5}
    )
    assert resp.status_code == 200

    silenced = _status(client, org_id, requirement["id"], building["id"])
    assert silenced["status"] == "CURRENT"


def test_lowering_grace_period_turns_unknown_into_missing_evidence(client):
    org_id, requirement, building = _setup(client)
    # Within the default 30-day grace (UNKNOWN) but outside a lowered
    # 10-day grace (MISSING_EVIDENCE) once the config change below lands.
    twenty_days_ago = (date.today() - timedelta(days=20)).isoformat()
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": twenty_days_ago,
        },
    )
    unknown = _status(client, org_id, requirement["id"], building["id"])
    assert unknown["status"] == "UNKNOWN"

    resp = client.patch(
        "/api/v1/compliance/status-config", headers={"X-Organisation-Id": org_id}, json={"never_assessed_grace_days": 10}
    )
    assert resp.status_code == 200

    missing = _status(client, org_id, requirement["id"], building["id"])
    assert missing["status"] == "MISSING_EVIDENCE"


def test_status_config_write_requires_operations_compliance_permission(client):
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
    resp = client.patch(
        "/api/v1/compliance/status-config", headers={"X-Organisation-Id": org_id}, json={"due_soon_days": 5}
    )
    assert resp.status_code == 403
