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


def _add_development(client, org_id, **overrides):
    payload = {"name": "Riverside Gardens"}
    payload.update(overrides)
    return client.post("/api/v1/developments", headers={"X-Organisation-Id": org_id}, json=payload).json()


def _add_building(client, org_id, **overrides):
    payload = {"name": "Block A"}
    payload.update(overrides)
    return client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json=payload).json()


def test_add_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.post(
        "/api/v1/developments",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Riverside Gardens", "address": "Riverside Way", "planning_reference": "PL/2026/001"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["development_reference"] == "DEV-000001"
    assert body["status"] == "CONCEPT"
    assert body["planning_reference"] == "PL/2026/001"


def test_add_building_standalone_and_under_a_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    standalone = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Standalone Block"}
    ).json()
    assert standalone["development_id"] is None
    assert standalone["building_reference"] == "BLD-000001"

    dev = _add_development(client, org_id)
    linked = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Block A", "development_id": dev["id"]},
    ).json()
    assert linked["development_id"] == dev["id"]
    assert linked["building_reference"] == "BLD-000002"


def test_add_building_under_missing_development_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"name": "Block A", "development_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_add_floor(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = _add_building(client, org_id)

    resp = client.post(
        "/api/v1/floors",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"], "name": "Ground Floor", "level_index": 0},
    )
    assert resp.status_code == 201
    assert resp.json()["building_id"] == building["id"]

    floors = client.get(
        "/api/v1/floors", headers={"X-Organisation-Id": org_id}, params={"building_id": building["id"]}
    ).json()
    assert len(floors) == 1


def test_property_can_be_linked_directly_to_a_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = _add_development(client, org_id)

    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Plot 1", "development_id": dev["id"]},
    ).json()
    assert prop["development_id"] == dev["id"]
    assert prop["building_id"] is None


def test_property_linked_to_floor_derives_building_and_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = _add_development(client, org_id)
    building = _add_building(client, org_id, development_id=dev["id"])
    floor = client.post(
        "/api/v1/floors",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"], "name": "1st Floor"},
    ).json()

    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "floor_id": floor["id"]},
    ).json()
    assert prop["floor_id"] == floor["id"]
    assert prop["building_id"] == building["id"]
    assert prop["development_id"] == dev["id"]


def test_property_with_mismatched_building_and_floor_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building_a = _add_building(client, org_id, name="Block A")
    building_b = _add_building(client, org_id, name="Block B")
    floor_on_a = client.post(
        "/api/v1/floors",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building_a["id"], "name": "Ground Floor"},
    ).json()

    resp = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "building_id": building_b["id"], "floor_id": floor_on_a["id"]},
    )
    assert resp.status_code == 400


def test_property_with_missing_building_id_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"address": "Flat 1", "building_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_development_hierarchy_view(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = _add_development(client, org_id)
    building = _add_building(client, org_id, development_id=dev["id"])
    floor = client.post(
        "/api/v1/floors",
        headers={"X-Organisation-Id": org_id},
        json={"building_id": building["id"], "name": "Ground Floor", "level_index": 0},
    ).json()

    # One property fully drilled down to the floor...
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "floor_id": floor["id"]},
    )
    # ...one linked to the building only (no floor assigned yet)...
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 2", "building_id": building["id"]},
    )
    # ...and one linked to the development only (no building assigned yet).
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Plot 3", "development_id": dev["id"]},
    )

    hierarchy = client.get(
        f"/api/v1/developments/{dev['id']}/hierarchy", headers={"X-Organisation-Id": org_id}
    ).json()
    assert hierarchy["unbuilt_property_count"] == 1
    assert len(hierarchy["buildings"]) == 1
    b = hierarchy["buildings"][0]
    assert b["unfloored_property_count"] == 1
    assert len(b["floors"]) == 1
    assert b["floors"][0]["property_count"] == 1


def test_space_can_belong_to_a_building_directly(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = _add_building(client, org_id)

    resp = client.post(
        "/api/v1/properties/00000000-0000-0000-0000-000000000000/spaces",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Communal Hall"},
    )
    assert resp.status_code == 404  # confirms the property-scoped route still requires a real property

    # A building-only space isn't exposed via the property-scoped router in
    # Sprint 6 (no /buildings/{id}/spaces route yet) — this test documents
    # that create_space itself supports it, exercised at the service layer.
    import app.core.db as db_module
    from app.development.service import create_space
    from app.core.provenance import SourceType
    import uuid

    db = db_module.SessionLocal()
    try:
        space = create_space(
            db,
            uuid.UUID(org_id),
            name="Communal Hall",
            building_id=uuid.UUID(building["id"]),
            source_type=SourceType.MANUAL,
        )
        db.commit()
        assert space.property_id is None
        assert space.building_id == uuid.UUID(building["id"])
    finally:
        db.close()


def test_space_requires_a_parent(client):
    from app.development.service import HierarchyMismatchError, create_space
    from app.core.provenance import SourceType
    import app.core.db as db_module
    import pytest
    import uuid

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    db = db_module.SessionLocal()
    try:
        with pytest.raises(HierarchyMismatchError):
            create_space(
                db, uuid.UUID(signup["organisation_id"]), name="Orphan Space", source_type=SourceType.MANUAL
            )
    finally:
        db.close()


def test_hierarchy_is_scoped_per_organisation(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    dev_a = _add_development(client, signup_a["organisation_id"])

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()

    resp = client.get(
        f"/api/v1/developments/{dev_a['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
