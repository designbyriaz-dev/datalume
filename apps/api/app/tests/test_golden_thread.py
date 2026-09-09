import io


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


def test_golden_thread_composes_building_specifications_and_components(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    building = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Block A", "building_control_reference": "BC-2024-001"},
    ).json()

    client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "building",
            "related_entity_id": building["id"],
            "title": "Envelope specification",
        },
    )

    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "building_id": building["id"], "manufacturer": "Worcester"},
    ).json()

    component_spec = client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={
            "related_entity_type": "component",
            "related_entity_id": component["id"],
            "title": "Boiler installation spec",
        },
    ).json()
    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={
            "specification_id": component_spec["id"],
            "proposed_value": {"title": "Boiler installation spec (revised)"},
            "reason": "Manufacturer discontinued the specified model",
        },
    ).json()
    client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={
            "title": "Boiler commissioning certificate",
            "document_type": "CERTIFICATE",
            "related_entity_type": "component",
            "related_entity_id": component["id"],
        },
        files={"file": ("cert.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
    )

    resp = client.get(f"/api/v1/buildings/{building['id']}/golden-thread", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()

    assert body["building_reference"] == building["building_reference"]
    assert len(body["specifications"]) == 1
    assert body["specifications"][0]["title"] == "Envelope specification"
    assert body["external_references"] == {"BUILDING_CONTROL_REFERENCE": "BC-2024-001"}

    assert len(body["components"]) == 1
    comp = body["components"][0]
    assert comp["id"] == component["id"]
    assert comp["component_type_name"] == "Boilers"
    assert len(comp["specifications"]) == 1
    assert comp["specifications"][0]["title"] == "Boiler installation spec"
    assert len(comp["evidence"]) == 1
    assert comp["evidence"][0]["title"] == "Boiler commissioning certificate"
    assert comp["responsible_party"]["created_by_name"] == "Jamie Ward"
    assert comp["responsible_party"]["source_type"] == "MANUAL"
    assert len(comp["changes"]) == 1
    assert comp["changes"][0]["id"] == change["id"]
    assert comp["changes"][0]["status"] == "PROPOSED"

    assert body["not_yet_available"] == ["inspections (Sprint 16)", "handover_records (Sprint 12)"]


def test_golden_thread_includes_components_attached_via_property(client):
    """A component doesn't need building_id set directly — one attached
    to a property that belongs to the building must still show up, since
    the Golden Thread is meant to be complete for the building, not just
    the components with a direct FK."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1, Block A", "building_id": building["id"]},
    ).json()
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    kitchen_type_id = next(t["id"] for t in types if t["code"] == "KITCHENS")
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": kitchen_type_id, "property_id": prop["id"]},
    ).json()

    resp = client.get(f"/api/v1/buildings/{building['id']}/golden-thread", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    component_ids = [c["id"] for c in resp.json()["components"]]
    assert component_ids == [component["id"]]


def test_golden_thread_for_missing_building_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get(
        "/api/v1/buildings/00000000-0000-0000-0000-000000000000/golden-thread",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 404
