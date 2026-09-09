"""Board Assurance report — architecture/04-operations-domain.md §6,
spec item 57: a read-only rollup, gated by the `reports.board`
permission (EXECUTIVE, OWNER, ADMIN only)."""

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


def _domain_id(client, org_id, code):
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    return next(d["id"] for d in domains if d["code"] == code)


def test_assurance_report_rolls_up_statuses_and_hazards_by_domain(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    gas_domain = _domain_id(client, org_id, "GAS_SAFETY")
    fire_domain = _domain_id(client, org_id, "FIRE_SAFETY")

    gas_req = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": gas_domain, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    fire_req = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": fire_domain, "code": "FIRE-001", "title": "Fire risk assessment", "effective_date": "2024-01-01"},
    ).json()

    building_a = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    building_b = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}).json()

    # Block A: gas requirement CURRENT.
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={"requirement_id": gas_req["id"], "entity_type": "building", "entity_id": building_a["id"], "applicable_from": "2024-01-01"},
    )
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": gas_req["id"],
            "entity_type": "building",
            "entity_id": building_a["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2026-01-01",
            "result": "SATISFACTORY",
            "next_due_date": (date.today() + timedelta(days=200)).isoformat(),
        },
    )

    # Block B: gas requirement OVERDUE (hard deadline, past due).
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={"requirement_id": gas_req["id"], "entity_type": "building", "entity_id": building_b["id"], "applicable_from": "2024-01-01"},
    )
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": gas_req["id"],
            "entity_type": "building",
            "entity_id": building_b["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2025-01-01",
            "result": "SATISFACTORY",
            "next_due_date": (date.today() - timedelta(days=5)).isoformat(),
        },
    )

    # Block A: fire requirement NOT_APPLICABLE (no applicability set) —
    # skipped entirely, since assurance only rolls up currently-
    # applicable pairs. Instead give it an OPEN_ACTION.
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={"requirement_id": fire_req["id"], "entity_type": "building", "entity_id": building_a["id"], "applicable_from": "2024-01-01"},
    )
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": fire_req["id"],
            "entity_type": "building",
            "entity_id": building_a["id"],
            "inspector": "FRA Assessor",
            "inspection_date": "2026-01-01",
            "result": "UNSATISFACTORY",
            "next_due_date": (date.today() + timedelta(days=200)).isoformat(),
        },
    )
    client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": fire_req["id"],
            "entity_type": "building",
            "entity_id": building_a["id"],
            "description": "Fire door replacement",
            "deadline": (date.today() + timedelta(days=10)).isoformat(),
        },
    )

    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": "2026-01-01", "severity": "HIGH"},
    )

    resp = client.get("/api/v1/compliance/assurance-report", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()

    gas_summary = next(d for d in body["domains"] if d["domain_code"] == "GAS_SAFETY")
    assert gas_summary["status_counts"].get("CURRENT") == 1
    assert gas_summary["status_counts"].get("OVERDUE") == 1

    fire_summary = next(d for d in body["domains"] if d["domain_code"] == "FIRE_SAFETY")
    assert fire_summary["status_counts"].get("OPEN_ACTION") == 1
    assert fire_summary["open_actions"] == 1

    assert body["total_open_actions"] == 1
    assert body["total_overdue_actions"] == 0
    assert body["hazard_status_counts"].get("REPORTED") == 1
    assert body["open_hazard_severity_counts"].get("HIGH") == 1


def test_assurance_report_property_filter_scopes_hazards(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop_a = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    prop_b = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 2"}).json()
    client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop_a["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": "2026-01-01"},
    )
    client.post(
        "/api/v1/hazards",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop_b["id"], "hazard_type": "EXCESS_COLD", "reported_date": "2026-01-01"},
    )

    resp = client.get(
        "/api/v1/compliance/assurance-report", headers={"X-Organisation-Id": org_id}, params={"property_id": prop_a["id"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert sum(body["hazard_status_counts"].values()) == 1


def test_assurance_report_requires_reports_board_permission(client):
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
    resp = client.get("/api/v1/compliance/assurance-report", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 403


def test_assurance_report_visible_to_executive_role(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        exec_user = User(
            email="exec@northstar-housing.example",
            name="Board Executive",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(exec_user)
        db.flush()
        exec_role = _get_or_create_role(db, "EXECUTIVE")
        db.add(
            Membership(
                user_id=exec_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=exec_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "exec@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.get("/api/v1/compliance/assurance-report", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
