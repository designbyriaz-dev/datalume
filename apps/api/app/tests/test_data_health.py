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


def _add_property(client, org_id, **overrides):
    payload = {"address": "1 Test Close"}
    payload.update(overrides)
    return client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json=payload).json()


def test_data_health_with_no_properties_scores_100(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get("/api/v1/data-health", headers={"X-Organisation-Id": signup["organisation_id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score_pct"] == 100.0
    assert body["findings"] == []


def test_data_health_flags_missing_fields(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _add_property(client, org_id, address="1 Complete Close", postcode="SW1A 1AA", uprn="1001", property_type="House")
    _add_property(client, org_id, address="2 Incomplete Close")  # missing postcode, uprn, property_type

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    check_codes_with_findings = {f["check_code"] for f in body["findings"]}
    # Neither property has a stock condition survey recorded, so both are
    # missing one — that check fires alongside the field-completeness ones.
    assert check_codes_with_findings == {
        "MISSING_UPRN",
        "MISSING_POSTCODE",
        "MISSING_PROPERTY_TYPE",
        "MISSING_STOCK_CONDITION_SURVEY",
    }
    assert body["score_pct"] < 100.0

    missing_type_check = next(c for c in body["checks"] if c["check_code"] == "MISSING_PROPERTY_TYPE")
    assert missing_type_check["applicable_count"] == 2
    assert missing_type_check["failing_count"] == 1


def test_data_health_flags_duplicate_addresses(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _add_property(client, org_id, address="1 Duplicate Close", postcode="SW1A 1AA", uprn="1", property_type="House")
    _add_property(
        client, org_id, address="1 DUPLICATE close", postcode="SW1A 1AA", uprn="2", property_type="House"
    )  # same address, different casing/whitespace

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    duplicate_findings = [f for f in body["findings"] if f["check_code"] == "DUPLICATE_PROPERTIES"]
    assert len(duplicate_findings) == 2  # both sides of the duplicate pair are flagged


def test_data_health_is_scoped_per_organisation(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    _add_property(client, signup_a["organisation_id"], address="1 Org A Close")

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()
    prop_b = _add_property(
        client,
        signup_b["organisation_id"],
        address="1 Org B Close",
        postcode="SW1A 1AA",
        uprn="1",
        property_type="House",
    )
    client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
        json={"property_id": prop_b["id"], "survey_date": "2026-01-01", "surveyor": "Surveyor Ltd"},
    )

    body_b = client.get("/api/v1/data-health", headers={"X-Organisation-Id": signup_b["organisation_id"]}).json()
    assert body_b["findings"] == []  # Org B's one property is complete — Org A's incomplete one must not leak in


def test_data_health_requires_org_header(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.get("/api/v1/data-health")
    assert resp.status_code == 400


def test_data_health_recompute_clears_stale_findings(client):
    """A property that gets fixed should stop appearing on the next check
    — findings are recomputed fresh each time, not accumulated forever."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _add_property(client, org_id, address="1 Fixable Close")

    first = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    # missing uprn, postcode, property_type, stock condition survey
    assert len(first["findings"]) == 4

    # UPRN lives in app.identifiers.models.ExternalReference since Sprint 7 —
    # record it through the real endpoint rather than a column assignment.
    client.post(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": org_id},
        json={"entity_type": "property", "entity_id": prop["id"], "reference_type": "UPRN", "value": "999"},
    )
    client.post(
        "/api/v1/stock-condition-surveys",
        headers={"X-Organisation-Id": org_id},
        json={"property_id": prop["id"], "survey_date": "2026-01-01", "surveyor": "Surveyor Ltd"},
    )

    import app.core.db as db_module
    from app.development.models import Property
    import uuid as uuid_module

    db = db_module.SessionLocal()
    try:
        row = db.get(Property, uuid_module.UUID(prop["id"]))
        row.postcode = "SW1A 1AA"
        row.property_type = "House"
        db.commit()
    finally:
        db.close()

    second = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    assert second["findings"] == []
    assert second["score_pct"] == 100.0


def _boiler_type_id(client, org_id):
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    return next(t["id"] for t in types if t["code"] == "BOILERS")


def test_data_health_flags_orphan_components(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop = _add_property(client, org_id, address="1 Anchored Close", postcode="SW1A 1AA", uprn="1", property_type="House")

    # Linked to a real property — not an orphan.
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop["id"]},
    )
    # No development/building/property/space/parent link at all.
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id},
    )

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    orphan_findings = [f for f in body["findings"] if f["check_code"] == "ORPHAN_COMPONENT"]
    assert len(orphan_findings) == 1

    orphan_check = next(c for c in body["checks"] if c["check_code"] == "ORPHAN_COMPONENT")
    assert orphan_check["applicable_count"] == 2
    assert orphan_check["failing_count"] == 1


def test_data_health_flags_duplicate_components(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop = _add_property(client, org_id, address="1 Duplicated Close", postcode="SW1A 1AA", uprn="1", property_type="House")

    payload = {
        "component_type_id": boiler_type_id,
        "property_id": prop["id"],
        "manufacturer": "Worcester",
        "model": "Greenstar 8000",
    }
    client.post("/api/v1/components", headers={"X-Organisation-Id": org_id}, json=payload)
    client.post("/api/v1/components", headers={"X-Organisation-Id": org_id}, json=payload)
    # Different model at the same property — not a duplicate of the pair above.
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={**payload, "model": "Greenstar 30i"},
    )

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    duplicate_findings = [f for f in body["findings"] if f["check_code"] == "DUPLICATE_COMPONENT"]
    assert len(duplicate_findings) == 2  # both sides of the one true duplicate pair


def test_data_health_flags_missing_handover_information(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop_with_record = _add_property(client, org_id, address="1 Recorded Close")
    prop_without_record = _add_property(client, org_id, address="2 Unrecorded Close")
    development = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    import uuid as uuid_module

    import app.core.db as db_module
    from app.core.provenance import SourceType
    from app.development.models import HandoverRecord, Property, PropertyStatus

    db = db_module.SessionLocal()
    try:
        for prop_id in (prop_with_record["id"], prop_without_record["id"]):
            row = db.get(Property, uuid_module.UUID(prop_id))
            row.status = PropertyStatus.HANDED_OVER
        db.add(
            HandoverRecord(
                organisation_id=uuid_module.UUID(org_id),
                property_id=uuid_module.UUID(prop_with_record["id"]),
                development_id=uuid_module.UUID(development["id"]),
                readiness_score_pct=100.0,
                readiness_snapshot=[],
                source_type=SourceType.MANUAL,
            )
        )
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "MISSING_HANDOVER_INFORMATION"]
    assert len(findings) == 1
    assert findings[0]["affected_entity_id"] == prop_without_record["id"]

    check = next(c for c in body["checks"] if c["check_code"] == "MISSING_HANDOVER_INFORMATION")
    assert check["applicable_count"] == 2
    assert check["failing_count"] == 1


def _add_component(client, org_id, boiler_type_id, prop_id, **overrides):
    payload = {"component_type_id": boiler_type_id, "property_id": prop_id}
    payload.update(overrides)
    return client.post("/api/v1/components", headers={"X-Organisation-Id": org_id}, json=payload).json()


def test_data_health_flags_missing_serial_number(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop = _add_property(client, org_id, address="1 Serial Close")
    _add_component(client, org_id, boiler_type_id, prop["id"], serial_number="WB-1")
    unserialled = _add_component(client, org_id, boiler_type_id, prop["id"])

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "MISSING_SERIAL_NUMBER"]
    assert len(findings) == 1
    assert findings[0]["affected_entity_id"] == unserialled["id"]


def test_data_health_flags_missing_installation_date(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop = _add_property(client, org_id, address="1 Installed Close")
    _add_component(client, org_id, boiler_type_id, prop["id"], installation_date="2024-01-15")
    undated = _add_component(client, org_id, boiler_type_id, prop["id"])

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "MISSING_INSTALLATION_DATE"]
    assert len(findings) == 1
    assert findings[0]["affected_entity_id"] == undated["id"]


def test_data_health_flags_invalid_installation_date(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    boiler_type_id = _boiler_type_id(client, org_id)
    prop = _add_property(client, org_id, address="1 Future Close")
    _add_component(client, org_id, boiler_type_id, prop["id"], installation_date="2024-01-15")
    future = _add_component(client, org_id, boiler_type_id, prop["id"], installation_date="2099-01-01")

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "INVALID_INSTALLATION_DATE"]
    assert len(findings) == 1
    assert findings[0]["affected_entity_id"] == future["id"]

    check = next(c for c in body["checks"] if c["check_code"] == "INVALID_INSTALLATION_DATE")
    # Only the two dated components are applicable — the undated case is
    # check_missing_installation_date's concern, not double-counted here.
    assert check["applicable_count"] == 2
    assert check["failing_count"] == 1


def test_data_health_flags_conflicting_external_references(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _add_property(client, org_id, address="1 Conflicted Close")

    client.post(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": org_id},
        json={"entity_type": "property", "entity_id": prop["id"], "reference_type": "UPRN", "value": "111"},
    )
    client.post(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": org_id},
        json={"entity_type": "property", "entity_id": prop["id"], "reference_type": "UPRN", "value": "222"},
    )

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "CONFLICTING_EXTERNAL_REFERENCE"]
    # Both conflicting rows are flagged, same "both sides" convention as
    # check_duplicate_properties.
    assert len(findings) == 2
    assert all(f["affected_entity_id"] == prop["id"] for f in findings)


def test_data_health_flags_duplicate_documents(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    def upload(title):
        return client.post(
            "/api/v1/documents",
            headers={"X-Organisation-Id": org_id},
            data={"title": title, "document_type": "EVIDENCE"},
            files={"file": ("evidence.pdf", io.BytesIO(b"identical content"), "application/pdf")},
        ).json()

    first = upload("Fire door certificate")
    second = upload("Fire door certificate (copy)")
    upload_other = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={"title": "Unrelated certificate", "document_type": "EVIDENCE"},
        files={"file": ("other.pdf", io.BytesIO(b"different content"), "application/pdf")},
    ).json()

    body = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    findings = [f for f in body["findings"] if f["check_code"] == "DUPLICATE_DOCUMENT"]
    flagged_ids = {f["affected_entity_id"] for f in findings}
    assert flagged_ids == {first["id"], second["id"]}
    assert upload_other["id"] not in flagged_ids
