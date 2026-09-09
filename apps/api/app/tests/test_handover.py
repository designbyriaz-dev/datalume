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


def _login_as_owner(client, **signup_overrides):
    return client.post("/api/v1/auth/signup", json=_signup_payload(**signup_overrides)).json()


def test_readiness_is_zero_with_no_properties(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    resp = client.get(f"/api/v1/developments/{dev['id']}/handover-readiness", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score_pct"] == 0.0
    assert body["ready"] is False
    assert "No properties recorded for this development" in body["missing"]
    codes = {c["check_code"] for c in body["checks"]}
    assert codes == {
        "PROPERTIES_CREATED",
        "COMPONENTS_CAPTURED",
        "REQUIRED_COMPONENT_FIELDS",
        "WARRANTIES_RECEIVED",
        "CERTIFICATES_RECEIVED",
        "COMMISSIONING_EVIDENCE",
        "OM_DOCUMENTATION",
        "BUILDING_CONTROL_REFERENCE",
        "OUTSTANDING_DEFECTS",
    }


def _fully_ready_development(client, org_id):
    """Builds one development with one building, one property, one
    component, and every piece of evidence the readiness engine checks
    for — used as the "should score 100%" baseline in several tests."""
    dev = client.post(
        "/api/v1/developments",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Riverside Gardens", "building_control_reference": None},
    ).json()
    building = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Block A", "development_id": dev["id"], "building_control_reference": "BC-2024-001"},
    ).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1, Block A", "development_id": dev["id"], "building_id": building["id"]},
    ).json()
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={
            "component_type_id": boiler_type_id,
            "property_id": prop["id"],
            "development_id": dev["id"],
            "manufacturer": "Worcester Bosch",
            "model": "Greenstar 8000",
            "serial_number": "WB-9981",
            "installation_date": "2024-01-15",
        },
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
    for title, document_type, related_entity_type, related_entity_id in [
        ("Boiler electrical certificate", "ELECTRICAL_CERTIFICATE", "component", component["id"]),
        ("Boiler commissioning record", "COMMISSIONING_RECORD", "component", component["id"]),
        ("Development O&M manual", "O&M_MANUAL", "development", dev["id"]),
    ]:
        client.post(
            "/api/v1/documents",
            headers={"X-Organisation-Id": org_id},
            data={
                "title": title,
                "document_type": document_type,
                "related_entity_type": related_entity_type,
                "related_entity_id": related_entity_id,
            },
            files={"file": ("f.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
        )
    return dev, building, prop, component


def test_readiness_is_100_percent_when_everything_is_captured(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev, _, _, _ = _fully_ready_development(client, org_id)

    resp = client.get(f"/api/v1/developments/{dev['id']}/handover-readiness", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score_pct"] == 100.0
    assert body["ready"] is True
    assert body["missing"] == []


def test_readiness_flags_outstanding_defects(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev, _, prop, _ = _fully_ready_development(client, org_id)
    client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={
            "category": "Windows",
            "description": "Sticking window",
            "reported_date": "2026-01-01",
            "property_id": prop["id"],
            "development_id": dev["id"],
        },
    )

    resp = client.get(f"/api/v1/developments/{dev['id']}/handover-readiness", headers={"X-Organisation-Id": org_id})
    body = resp.json()
    assert body["score_pct"] < 100.0
    assert any("outstanding defect" in item for item in body["missing"])


def test_authorise_handover_blocked_below_threshold_without_override(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    resp = client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise", headers={"X-Organisation-Id": org_id}, json={}
    )
    assert resp.status_code == 400


def test_authorise_handover_with_override_reason_succeeds_below_threshold(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": dev["id"], "status": "READY_FOR_HANDOVER"},
    ).json()

    resp = client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise",
        headers={"X-Organisation-Id": org_id},
        json={"override_reason": "Client accepted risk on outstanding O&M documentation"},
    )
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    assert records[0]["property_id"] == prop["id"]
    assert records[0]["override_reason"] == "Client accepted risk on outstanding O&M documentation"
    assert records[0]["readiness_score_pct"] < 100.0
    assert len(records[0]["readiness_snapshot"]) == 9

    updated_prop = client.get(f"/api/v1/properties/{prop['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert updated_prop["status"] == "HANDED_OVER"


def test_authorise_handover_only_transitions_ready_for_handover_properties(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev, _, ready_prop, _ = _fully_ready_development(client, org_id)
    client.post(
        f"/api/v1/properties/{ready_prop['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "READY_FOR_HANDOVER"},
    )
    not_ready_prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 2", "development_id": dev["id"]},  # stays OPERATIONAL (default), not in scope
    ).json()

    # The second, component-less property drags the development's score
    # below 100% — an override is used here purely to get past that gate
    # so this test can isolate what it's actually checking (which
    # properties get transitioned), not re-test the threshold guard
    # covered by test_authorise_handover_blocked_below_threshold_without_override.
    resp = client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise",
        headers={"X-Organisation-Id": org_id},
        json={"override_reason": "Second property still under construction, phased handover"},
    )
    assert resp.status_code == 200
    records = resp.json()
    property_ids = [r["property_id"] for r in records]
    assert ready_prop["id"] in property_ids
    assert not_ready_prop["id"] not in property_ids

    untouched = client.get(f"/api/v1/properties/{not_ready_prop['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert untouched["status"] == "OPERATIONAL"


def test_cannot_set_handed_over_status_directly(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}
    ).json()

    resp = client.post(
        f"/api/v1/properties/{prop['id']}/status",
        headers={"X-Organisation-Id": org_id},
        json={"status": "HANDED_OVER"},
    )
    assert resp.status_code == 400


def test_handover_records_history(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": dev["id"], "status": "READY_FOR_HANDOVER"},
    )
    client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise",
        headers={"X-Organisation-Id": org_id},
        json={"override_reason": "Pilot scheme sign-off"},
    )

    resp = client.get(f"/api/v1/developments/{dev['id']}/handover-records", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_handover_readiness_weights_default_and_update(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]

    resp = client.get("/api/v1/handover-readiness-weights", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    weights = {w["check_code"]: w["weight"] for w in resp.json()}
    assert weights["COMPONENTS_CAPTURED"] == 0.15

    update = client.patch(
        "/api/v1/handover-readiness-weights/COMPONENTS_CAPTURED",
        headers={"X-Organisation-Id": org_id},
        json={"weight": 0.30},
    )
    assert update.status_code == 200
    assert update.json()["weight"] == 0.30

    resp2 = client.get("/api/v1/handover-readiness-weights", headers={"X-Organisation-Id": org_id})
    weights2 = {w["check_code"]: w["weight"] for w in resp2.json()}
    assert weights2["COMPONENTS_CAPTURED"] == 0.30


def test_configured_weight_changes_the_readiness_score(client):
    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1", "development_id": dev["id"]}
    )
    baseline = client.get(
        f"/api/v1/developments/{dev['id']}/handover-readiness", headers={"X-Organisation-Id": org_id}
    ).json()["score_pct"]

    # Zero out every check except PROPERTIES_CREATED (which already passes) —
    # the score should jump to 100% since only a passing check has any weight.
    for code in [
        "COMPONENTS_CAPTURED",
        "REQUIRED_COMPONENT_FIELDS",
        "WARRANTIES_RECEIVED",
        "CERTIFICATES_RECEIVED",
        "COMMISSIONING_EVIDENCE",
        "OM_DOCUMENTATION",
        "BUILDING_CONTROL_REFERENCE",
        "OUTSTANDING_DEFECTS",
    ]:
        client.patch(
            f"/api/v1/handover-readiness-weights/{code}", headers={"X-Organisation-Id": org_id}, json={"weight": 0.0}
        )

    reweighted = client.get(
        f"/api/v1/developments/{dev['id']}/handover-readiness", headers={"X-Organisation-Id": org_id}
    ).json()["score_pct"]
    assert reweighted == 100.0
    assert reweighted > baseline


def test_handover_authorise_requires_handover_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = _login_as_owner(client)
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    db = db_module.SessionLocal()
    try:
        # DEVELOPMENT_MANAGER has development.write but not
        # development.handover — the permission this whole workflow was
        # created for back in Sprint 1 and unused until now.
        manager_user = User(
            email="manager@northstar-housing.example",
            name="Dev Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "DEVELOPMENT_MANAGER")
        db.add(
            Membership(
                user_id=manager_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=manager_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "manager@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        f"/api/v1/developments/{dev['id']}/handover/authorise", headers={"X-Organisation-Id": org_id}, json={}
    )
    assert resp.status_code == 403


def test_handover_from_other_org_is_not_found(client):
    signup_a = _login_as_owner(client)
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"name": "Riverside Gardens"}
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = _login_as_owner(client, email="other@example.com", organisation_name="Other Org")
    resp = client.get(
        f"/api/v1/developments/{dev['id']}/handover-readiness",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
    )
    assert resp.status_code == 404
