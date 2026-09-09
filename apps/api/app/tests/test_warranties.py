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


def test_add_warranty_against_a_component(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components", headers={"X-Organisation-Id": org_id}, json={"component_type_id": boiler_type_id}
    ).json()

    resp = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer - Boiler",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
            "terms_reference": "WB-WARR-9981",
            "component_id": component["id"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["warranty_reference"] == "WAR-000001"
    assert body["status"] == "ACTIVE"
    assert body["component_id"] == component["id"]
    assert body["is_expired"] is False
    assert body["days_until_expiry"] > 0


def test_warranty_expiry_before_start_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2023-01-15",
        },
    )
    assert resp.status_code == 400


def test_expired_warranty_reads_as_expired(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    warranty = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2010-01-15",
            "expiry_date": "2011-01-15",
        },
    ).json()
    assert warranty["is_expired"] is True
    assert warranty["days_until_expiry"] < 0
    assert warranty["status"] == "ACTIVE"  # status column itself is untouched — expiry is computed, not stored


def test_void_warranty(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    warranty = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
        },
    ).json()

    resp = client.post(f"/api/v1/warranties/{warranty['id']}/void", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "VOID"


def test_list_warranties_expiring_within_days(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    soon = (date.today() + timedelta(days=10)).isoformat()
    far = (date.today() + timedelta(days=3650)).isoformat()

    expiring_soon = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={"provider": "A", "warranty_type": "x", "start_date": "2020-01-01", "expiry_date": soon},
    ).json()
    client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={"provider": "B", "warranty_type": "x", "start_date": "2020-01-01", "expiry_date": far},
    )

    resp = client.get(
        "/api/v1/warranties", headers={"X-Organisation-Id": org_id}, params={"expiring_within_days": 30}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == expiring_soon["id"]


def test_warranty_with_document_id(client):
    import io

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    doc = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={"title": "Warranty terms", "document_type": "WARRANTY"},
        files={"file": ("terms.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
    ).json()

    resp = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
            "document_id": doc["id"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["document_id"] == doc["id"]


def test_warranty_with_missing_document_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
            "document_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404


def test_warranty_write_requires_permission(client):
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
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
        },
    )
    assert resp.status_code == 403


def test_warranty_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    warranty = client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
        },
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/warranties/{warranty['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
