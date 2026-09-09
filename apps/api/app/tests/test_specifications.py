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


def test_add_specification_against_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()

    resp = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "building",
            "related_entity_id": building["id"],
            "title": "External wall insulation system",
            "description": "EWI system per NHBC standards",
            "effective_date": "2024-03-01",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["specification_reference"] == "SPEC-000001"
    assert body["revision"] == "A"
    assert body["status"] == "ACTIVE"
    assert body["related_entity_type"] == "building"
    assert body["related_entity_id"] == building["id"]
    assert body["approved_by"] is None
    assert body["approved_at"] is None


def test_specification_against_unsupported_entity_type_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "development_phase",
            "related_entity_id": str(uuid.uuid4()),
            "title": "Bogus attachment point",
        },
    )
    assert resp.status_code == 400


def test_specification_against_missing_entity_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "building",
            "related_entity_id": "00000000-0000-0000-0000-000000000000",
            "title": "Attached to nothing",
        },
    )
    assert resp.status_code == 404


def test_specification_revision_supersedes_previous_and_keeps_reference(client):
    """"A change must NOT simply overwrite the previous specification"
    (spec §26) — the old row is marked SUPERSEDED, never edited in
    place, and the new row keeps the same specification_reference."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    original = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    ).json()

    revised = client.post(
        f"/api/v1/specifications/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"revision": "B", "description": "Updated after value engineering", "effective_date": "2024-06-01"},
    )
    assert revised.status_code == 201
    revised_body = revised.json()
    assert revised_body["specification_reference"] == original["specification_reference"]
    assert revised_body["revision"] == "B"
    assert revised_body["status"] == "ACTIVE"
    assert revised_body["title"] == "Roofing spec"  # carried forward, not re-supplied
    assert revised_body["description"] == "Updated after value engineering"

    previous = client.get(
        f"/api/v1/specifications/{original['id']}", headers={"X-Organisation-Id": org_id}
    ).json()
    assert previous["status"] == "SUPERSEDED"
    assert previous["superseded_date"] == "2024-06-01"

    detail = client.get(
        f"/api/v1/specifications/{revised_body['id']}", headers={"X-Organisation-Id": org_id}
    ).json()
    assert len(detail["versions"]) == 2
    assert [v["revision"] for v in detail["versions"]] == ["A", "B"]


def test_revising_a_superseded_specification_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    original = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    ).json()
    client.post(
        f"/api/v1/specifications/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"revision": "B"},
    )

    resp = client.post(
        f"/api/v1/specifications/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"revision": "C"},
    )
    assert resp.status_code == 400


def test_approve_specification_sets_approved_by_and_at(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    spec = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    ).json()
    assert spec["approved_by"] is None

    resp = client.post(f"/api/v1/specifications/{spec['id']}/approve", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved_by"] == signup["user_id"]
    assert body["approved_at"] is not None


def test_specification_against_a_component(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components", headers={"X-Organisation-Id": org_id}, json={"component_type_id": boiler_type_id}
    ).json()

    resp = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "component",
            "related_entity_id": component["id"],
            "title": "Boiler installation specification",
            "related_component_type": "Boilers",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["related_entity_id"] == component["id"]


def test_list_specifications_filters_by_related_entity_and_excludes_superseded_by_default(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building_a = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    building_b = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}
    ).json()
    spec_a = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "building", "related_entity_id": building_a["id"], "title": "Spec A"},
    ).json()
    client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "building", "related_entity_id": building_b["id"], "title": "Spec B"},
    )
    client.post(
        f"/api/v1/specifications/{spec_a['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"revision": "B"},
    )

    filtered = client.get(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        params={"related_entity_type": "building", "related_entity_id": building_a["id"]},
    ).json()
    assert len(filtered) == 1
    assert filtered[0]["revision"] == "B"  # current_only excludes the superseded A revision


def test_specification_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": signup["organisation_id"]}, json={"name": "Block A"}
    ).json()

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
        "/api/v1/specifications",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    )
    assert resp.status_code == 403


def test_specification_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"name": "Block A"}
    ).json()
    spec = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/specifications/{spec['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
