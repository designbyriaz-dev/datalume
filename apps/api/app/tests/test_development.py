import io
import uuid

from app.auth.models import Membership, MembershipStatus, User
from app.auth.router import _get_or_create_role
from app.core.security import hash_password


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


def test_manual_add_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "1 Test Close", "postcode": "SW1A 1AA", "property_type": "House"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["property_reference"] == "PROP-000001"
    assert body["source_type"] == "MANUAL"
    assert body["source_dataset_id"] is None
    assert body["status"] == "OPERATIONAL"


def test_property_reference_increments_per_organisation(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    first = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 First St"}
    ).json()
    second = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "2 Second St"}
    ).json()
    assert first["property_reference"] == "PROP-000001"
    assert second["property_reference"] == "PROP-000002"


def test_imported_property_carries_provenance_back_to_the_dataset(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    csv_text = "Property Address,Type\n42 Provenance Way,House\n"
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": "PROPERTIES", "name": "Provenance test"},
        files={"file": ("p.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    ).json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Property Address": "address", "Type": "property_type"}},
    )
    trigger_resp = client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})
    assert trigger_resp.status_code == 202

    import app.core.db as db_module
    from app.worker.jobs.ingestion import process_pending_import_jobs

    db = db_module.SessionLocal()
    try:
        process_pending_import_jobs(db)
    finally:
        db.close()

    properties = client.get("/api/v1/properties", headers={"X-Organisation-Id": org_id}).json()
    assert len(properties) == 1
    prop = properties[0]
    assert prop["source_dataset_id"] == upload["dataset_id"]
    assert prop["original_reference"] == "row 1"


def test_add_property_requires_development_write_permission(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()

    import app.core.db as db_module

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
                organisation_id=uuid.UUID(signup["organisation_id"]),
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
        "/api/v1/properties",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"address": "1 Test Close"},
    )
    assert resp.status_code == 403


def test_add_and_list_spaces(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 Test Close"}
    ).json()

    resp = client.post(
        f"/api/v1/properties/{prop['id']}/spaces",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Kitchen", "space_type": "ROOM"},
    )
    assert resp.status_code == 201
    assert resp.json()["property_id"] == prop["id"]

    spaces = client.get(f"/api/v1/properties/{prop['id']}/spaces", headers={"X-Organisation-Id": org_id}).json()
    assert len(spaces) == 1
    assert spaces[0]["name"] == "Kitchen"


def test_space_on_property_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"address": "1 Test Close"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()

    resp = client.post(
        f"/api/v1/properties/{prop['id']}/spaces",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
        json={"name": "Kitchen"},
    )
    assert resp.status_code == 404


def test_property_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"address": "1 Test Close"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other2@example.com", organisation_name="Other Org 2"),
    ).json()

    resp = client.get(
        f"/api/v1/properties/{prop['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
