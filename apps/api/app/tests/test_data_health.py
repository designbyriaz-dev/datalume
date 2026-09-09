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
    assert check_codes_with_findings == {"MISSING_UPRN", "MISSING_POSTCODE", "MISSING_PROPERTY_TYPE"}
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
    _add_property(
        client,
        signup_b["organisation_id"],
        address="1 Org B Close",
        postcode="SW1A 1AA",
        uprn="1",
        property_type="House",
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
    assert len(first["findings"]) == 3  # missing uprn, postcode, property_type

    import app.core.db as db_module
    from app.development.models import Property
    import uuid as uuid_module

    db = db_module.SessionLocal()
    try:
        row = db.get(Property, uuid_module.UUID(prop["id"]))
        row.uprn = "999"
        row.postcode = "SW1A 1AA"
        row.property_type = "House"
        db.commit()
    finally:
        db.close()

    second = client.get("/api/v1/data-health", headers={"X-Organisation-Id": org_id}).json()
    assert second["findings"] == []
    assert second["score_pct"] == 100.0
