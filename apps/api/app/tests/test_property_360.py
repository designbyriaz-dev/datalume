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


def test_property_360_composes_everything_available(client):
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
        json={"address": "Flat 1, Block A", "development_id": dev["id"], "building_id": building["id"]},
    ).json()

    client.post(
        "/api/v1/specifications",
        headers={"X-Organisation-Id": org_id},
        json={"related_entity_type": "property", "related_entity_id": prop["id"], "title": "Kitchen spec"},
    )
    client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={
            "title": "EPC certificate",
            "document_type": "EPC",
            "related_entity_type": "property",
            "related_entity_id": prop["id"],
        },
        files={"file": ("epc.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
    )

    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop["id"], "manufacturer": "Worcester Bosch"},
    ).json()
    client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
            "component_id": component["id"],
        },
    )
    client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={
            "category": "Windows",
            "description": "Sticking window",
            "reported_date": "2026-01-01",
            "property_id": prop["id"],
        },
    )

    resp = client.get(f"/api/v1/properties/{prop['id']}/360", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()

    assert body["property"]["id"] == prop["id"]
    assert body["development"]["id"] == dev["id"]
    assert body["building"]["id"] == building["id"]
    assert body["floor"] is None
    assert len(body["specifications"]) == 1
    assert body["specifications"][0]["title"] == "Kitchen spec"
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["title"] == "EPC certificate"
    assert len(body["components"]) == 1
    assert body["components"][0]["id"] == component["id"]
    assert len(body["warranties"]) == 1
    assert body["warranties"][0]["provider"] == "Worcester Bosch"
    assert len(body["defects"]) == 1
    assert body["defects"][0]["category"] == "Windows"
    assert body["handover_record"] is None
    assert len(body["timeline"]) > 0
    assert any(e["action_code"] == "property.created" for e in body["timeline"])
    assert any(e["action_code"] == "component.created" for e in body["timeline"])
    assert "repairs (Sprint 14)" in body["not_yet_available"]


def test_property_360_includes_components_attached_via_space(client):
    """A component doesn't need property_id set directly — one attached
    to a space that belongs to the property must still show up, since
    Property 360 is meant to be complete for the property, not just the
    components with a direct FK (same reasoning Golden Thread's building
    view applies via property_id, Sprint 9)."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}
    ).json()
    space = client.post(
        f"/api/v1/properties/{prop['id']}/spaces",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Kitchen"},
    ).json()
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "space_id": space["id"]},
    ).json()

    resp = client.get(f"/api/v1/properties/{prop['id']}/360", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    component_ids = [c["id"] for c in resp.json()["components"]]
    assert component_ids == [component["id"]]


def test_property_360_shows_handover_record(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": dev["id"], "status": "READY_FOR_HANDOVER"},
    ).json()
    client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise",
        headers={"X-Organisation-Id": org_id},
        json={"override_reason": "Pilot scheme sign-off"},
    )

    resp = client.get(f"/api/v1/properties/{prop['id']}/360", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["property"]["status"] == "HANDED_OVER"
    assert body["handover_record"] is not None
    assert body["handover_record"]["override_reason"] == "Pilot scheme sign-off"


def test_property_360_data_health_findings_scoped_to_this_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop_a = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 A St"}
    ).json()
    client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "2 B St"})

    resp = client.get(f"/api/v1/properties/{prop_a['id']}/360", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    findings = resp.json()["data_health_findings"]
    assert all(f["affected_entity_id"] == prop_a["id"] for f in findings)
    assert any(f["check_code"] == "MISSING_PROPERTY_TYPE" for f in findings)


def test_property_360_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"address": "1 A St"}
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/properties/{prop['id']}/360", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
