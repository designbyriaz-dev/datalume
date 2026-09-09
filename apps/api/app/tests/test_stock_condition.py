"""Stock Condition Surveys — architecture/04-operations-domain.md §6."""

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


def _property(client, org_id, address="Flat 1"):
    return client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": address}).json()


def test_record_a_survey(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    resp = client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "survey_date": "2026-01-10",
            "surveyor": "Surveyor Ltd",
            "condition_ratings": {"roof": "GOOD", "windows": "POOR"},
            "next_survey_due": "2031-01-10",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["surveyor"] == "Surveyor Ltd"
    assert body["condition_ratings"] == {"roof": "GOOD", "windows": "POOR"}
    assert body["next_survey_due"] == "2031-01-10"


def test_survey_against_missing_property_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": str(uuid.uuid4()), "survey_date": "2026-01-10", "surveyor": "x"},
    )
    assert resp.status_code == 404


def test_list_surveys_filters_by_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop_a = _property(client, org_id, "Flat A")
    prop_b = _property(client, org_id, "Flat B")
    for prop in (prop_a, prop_b):
        client.post(
            "/api/v1/stock-condition-surveys",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "survey_date": "2026-01-10", "surveyor": "Surveyor Ltd"},
        )

    resp = client.get(
        "/api/v1/stock-condition-surveys", headers={"X-Organisation-Id": org_id}, params={"property_id": prop_a["id"]}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["property_id"] == prop_a["id"]


def test_data_health_flags_stale_survey(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)
    overdue = (date.today() - timedelta(days=10)).isoformat()
    client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "survey_date": "2020-01-01", "surveyor": "Surveyor Ltd", "next_survey_due": overdue},
    )

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    codes = {f["check_code"] for f in body["findings"]}
    assert "STALE_STOCK_CONDITION_SURVEY" in codes
    assert "MISSING_STOCK_CONDITION_SURVEY" not in codes  # a survey exists, it's just overdue


def test_asset_manager_can_record_a_survey(client):
    """ASSET_MANAGER gained operations.write in this sprint specifically
    so it can do this — regression guard against that RBAC change being
    reverted."""
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    db = db_module.SessionLocal()
    try:
        asset_user = User(
            email="asset@northstar-housing.example",
            name="Asset Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(asset_user)
        db.flush()
        asset_role = _get_or_create_role(db, "ASSET_MANAGER")
        db.add(
            Membership(
                user_id=asset_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=asset_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "asset@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "survey_date": "2026-01-10", "surveyor": "Surveyor Ltd"},
    )
    assert resp.status_code == 201


def test_survey_write_requires_operations_write_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _property(client, org_id)

    db = db_module.SessionLocal()
    try:
        viewer = User(
            email="viewer@northstar-housing.example",
            name="Viewer",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(viewer)
        db.flush()
        viewer_role = _get_or_create_role(db, "VIEWER")
        db.add(
            Membership(
                user_id=viewer.id,
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
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "survey_date": "2026-01-10", "surveyor": "Surveyor Ltd"},
    )
    assert resp.status_code == 403
