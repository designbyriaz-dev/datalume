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


def test_add_building_control_record_against_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Block A"}
    ).json()

    resp = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={
            "building_id": building["id"],
            "body": "Local Authority Building Control",
            "application_date": "2025-03-01",
            "application_reference": "BC-APP-1001",
            "bsr_reference": "BSR-5566",
        },
    )
    assert resp.status_code == 201
    out = resp.json()
    assert out["building_id"] == building["id"]
    assert out["development_id"] is None
    assert out["status"] == "SUBMITTED"
    assert out["application_date"] == "2025-03-01"
    assert out["application_reference"] == "BC-APP-1001"
    assert out["bsr_reference"] == "BSR-5566"
    assert out["approval_date"] is None


def test_add_building_control_record_against_a_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    development = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    resp = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"development_id": development["id"], "body": "Approved Inspector Ltd"},
    )
    assert resp.status_code == 201
    out = resp.json()
    assert out["development_id"] == development["id"]
    assert out["building_id"] is None


def test_building_control_record_with_missing_building_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"building_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


def test_approving_a_building_control_record_sets_status_date_and_completion_reference(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Block B"}
    ).json()
    record = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"]},
    ).json()

    resp = client.patch(
        f"/api/v1/building-control-records/{record['id']}",
        headers={"X-Organisation-Id": org_id},
        json={
            "status": "COMPLETED",
            "approval_date": "2025-06-15",
            "conditions": "Fire-stopping to be re-inspected post-handover.",
            "completion_reference": "BC-COMP-9001",
        },
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "COMPLETED"
    assert out["approval_date"] == "2025-06-15"
    assert out["conditions"] == "Fire-stopping to be re-inspected post-handover."
    assert out["completion_reference"] == "BC-COMP-9001"


def test_updating_a_building_control_record_with_an_invalid_status_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Block C"}
    ).json()
    record = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"]},
    ).json()

    resp = client.patch(
        f"/api/v1/building-control-records/{record['id']}",
        headers={"X-Organisation-Id": org_id},
        json={"status": "NOT_A_REAL_STATUS"},
    )
    assert resp.status_code == 400


def test_list_building_control_records_filters_by_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building_a = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    building_b = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}
    ).json()
    record_a = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building_a["id"]},
    ).json()
    client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building_b["id"]},
    )

    resp = client.get(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        params={"building_id": building_a["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == record_a["id"]


def test_evidence_can_be_linked_to_a_building_control_record(client):
    import io

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Block D"}
    ).json()
    record = client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"]},
    ).json()

    doc = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={
            "title": "Completion certificate",
            "document_type": "CERTIFICATE",
            "related_entity_type": "building_control_record",
            "related_entity_id": record["id"],
        },
        files={"file": ("completion.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
    ).json()

    docs = client.get(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        params={"related_entity_type": "building_control_record", "related_entity_id": record["id"]},
    ).json()
    assert len(docs) == 1
    assert docs[0]["id"] == doc["id"]


def test_building_control_record_write_requires_permission(client):
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
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": org_id},
        json={"body": "Local Authority Building Control"},
    )
    assert resp.status_code == 403


def test_building_control_records_are_tenant_isolated(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    client.post(
        "/api/v1/building-control-records",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"body": "Org A's Building Control body"},
    )

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        "/api/v1/building-control-records", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 200
    assert resp.json() == []
