import io
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


def test_component_types_catalog_is_seeded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get("/api/v1/component-types", headers={"X-Organisation-Id": signup["organisation_id"]})
    assert resp.status_code == 200
    codes = {t["code"] for t in resp.json()}
    assert {"ROOF", "BOILERS", "SMOKE_ALARMS", "LIFTS", "OTHER"} <= codes
    assert all(t["organisation_id"] is None for t in resp.json())  # all global at this point


def test_add_component_generates_reference_and_serial_number_is_external(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)

    resp = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={
            "component_type_id": boiler_type_id,
            "manufacturer": "Worcester",
            "model": "Greenstar 8000",
            "serial_number": "WB-123456",
            "installation_date": "2024-01-15",
            "expected_life_years": 15,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["component_reference"] == "COMP-000001"
    assert body["component_type_name"] == "Boilers"
    assert body["serial_number"] == "WB-123456"
    assert body["status"] == "ACTIVE"
    # 2024-01-15 + 15 years (round(15 * 365.25) days)
    assert body["indicative_replacement_date"] == "2039-01-15"


def test_indicative_replacement_date_is_null_without_both_inputs(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)

    resp = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "installation_date": "2024-01-15"},  # no expected_life_years
    ).json()
    assert resp["indicative_replacement_date"] is None


def test_component_parent_child_hierarchy(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    heating_type_id = next(t["id"] for t in types if t["code"] == "HEATING_SYSTEMS")
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")

    heating_system = client.post(
        "/api/v1/components", headers={"X-Organisation-Id": org_id}, json={"component_type_id": heating_type_id}
    ).json()
    boiler = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "parent_component_id": heating_system["id"]},
    ).json()
    assert boiler["parent_component_id"] == heating_system["id"]

    children = client.get(
        f"/api/v1/components/{heating_system['id']}/children", headers={"X-Organisation-Id": org_id}
    ).json()
    assert len(children) == 1
    assert children[0]["id"] == boiler["id"]


def test_component_can_attach_to_a_building_with_no_property(client):
    """spec §24: a component (e.g. a lift) can belong to a building
    directly, no specific property — unlike Property's hierarchy, this
    isn't cross-validated the same strict way."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    lift_type_id = next(t["id"] for t in types if t["code"] == "LIFTS")

    resp = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": lift_type_id, "building_id": building["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["building_id"] == building["id"]
    assert resp.json()["property_id"] is None


def test_component_with_missing_building_id_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    resp = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "building_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_list_components_filters_by_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop_a = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 A St"}
    ).json()
    prop_b = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "2 B St"}
    ).json()
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop_a["id"]},
    )
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop_b["id"]},
    )

    filtered = client.get(
        "/api/v1/components", headers={"X-Organisation-Id": org_id}, params={"property_id": prop_a["id"]}
    ).json()
    assert len(filtered) == 1
    assert filtered[0]["property_id"] == prop_a["id"]


def test_component_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    boiler_type_id = _boiler_type_id(client, signup["organisation_id"])

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
        "/api/v1/components",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"component_type_id": boiler_type_id},
    )
    assert resp.status_code == 403


def test_component_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    boiler_type_id = _boiler_type_id(client, signup_a["organisation_id"])
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"component_type_id": boiler_type_id},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/components/{component['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404


def test_component_type_matching_is_singular_plural_tolerant(client):
    """Regression test: a real CSV import (see
    test_csv_import_creates_components_and_custom_types) used "Boiler"
    against the seeded "Boilers" and would have silently created a
    duplicate custom type without this fallback."""
    from app.development.component_types import find_component_type_by_name
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        from app.development.component_types import ensure_component_type_catalog_seeded

        ensure_component_type_catalog_seeded(db)
        db.commit()

        match = find_component_type_by_name(db, org_id, "Boiler")
        assert match is not None
        assert match.code == "BOILERS"
    finally:
        db.close()


# --- CSV import ---------------------------------------------------------------


def test_csv_import_creates_components_and_custom_types(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    csv_text = (
        "Component Type,Manufacturer,Model,Serial Number,Installation Date\n"
        "Boiler,Worcester,Greenstar 8000,WB-1,2024-01-15\n"
        "Bespoke Ventilation Unit,AirCo,VX-2,SN-2,2024-02-01\n"
    )
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": "COMPONENTS", "name": "Component import test"},
        files={"file": ("components.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    ).json()

    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Component Type": "component_type",
                "Manufacturer": "manufacturer",
                "Model": "model",
                "Serial Number": "serial_number",
                "Installation Date": "installation_date",
            }
        },
    )
    result = client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id}
    ).json()
    assert result == {"rows_processed": 2, "entities_created": 2, "importer_registered": True}

    components = client.get("/api/v1/components", headers={"X-Organisation-Id": org_id}).json()
    assert len(components) == 2
    boiler = next(c for c in components if c["manufacturer"] == "Worcester")
    assert boiler["component_type_name"] == "Boilers"  # matched the seeded global type
    assert boiler["serial_number"] == "WB-1"
    assert boiler["installation_date"] == "2024-01-15"
    assert boiler["source_type"] == "FILE_UPLOAD"
    assert boiler["source_dataset_id"] == upload["dataset_id"]

    # "Bespoke Ventilation Unit" matches no seeded type — auto-created as
    # an org-specific custom type rather than failing the row (spec §22:
    # "org-extensible").
    custom = next(c for c in components if c["manufacturer"] == "AirCo")
    assert custom["component_type_name"] == "Bespoke Ventilation Unit"

    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    custom_type = next(t for t in types if t["name"] == "Bespoke Ventilation Unit")
    assert custom_type["organisation_id"] == org_id
