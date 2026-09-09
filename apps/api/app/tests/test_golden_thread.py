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

    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    gas_domain_id = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": gas_domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "component",
            "entity_id": component["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2026-01-15",
            "result": "SATISFACTORY",
        },
    )
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "Fire Risk Assessor Ltd",
            "inspection_date": "2026-02-01",
            "result": "ADVISORY",
        },
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
    assert len(comp["inspections"]) == 1
    assert comp["inspections"][0]["result"] == "SATISFACTORY"

    assert len(body["inspections"]) == 1
    assert body["inspections"][0]["result"] == "ADVISORY"

    # Sprint 16 closed the last gap this list used to name.
    assert body["not_yet_available"] == []
    assert body["handover_records"] == []


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


def test_golden_thread_includes_handover_records_for_properties_under_the_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    building = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Block A", "development_id": dev["id"]},
    ).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={
            "address": "Flat 1, Block A",
            "development_id": dev["id"],
            "building_id": building["id"],
            "status": "READY_FOR_HANDOVER",
        },
    ).json()
    client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise",
        headers={"X-Organisation-Id": org_id},
        json={"override_reason": "Pilot scheme sign-off"},
    )

    resp = client.get(f"/api/v1/buildings/{building['id']}/golden-thread", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    handover_records = resp.json()["handover_records"]
    assert len(handover_records) == 1
    assert handover_records[0]["property_id"] == prop["id"]
    assert handover_records[0]["override_reason"] == "Pilot scheme sign-off"


def test_golden_thread_for_missing_building_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get(
        "/api/v1/buildings/00000000-0000-0000-0000-000000000000/golden-thread",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 404
