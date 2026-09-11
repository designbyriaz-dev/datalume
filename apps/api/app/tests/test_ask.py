"""Ask DataLume — architecture/06-intelligence-layer.md §1-2. No
ANTHROPIC_API_KEY is set in this test environment, so every test here
exercises NullLLMProvider's templated-summary fallback — which is
itself the point: tool selection and grounding must work, and be
tested, entirely independently of whether an LLM is configured."""

import uuid
from datetime import date


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


def _ask(client, org_id, question, entity_type, entity_id):
    resp = client.post(
        "/api/v1/ask",
        headers={"X-Organisation-Id": org_id},
        json={"question": question, "entity_type": entity_type, "entity_id": entity_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_compliance_question_is_grounded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    gas_domain = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": gas_domain, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={"requirement_id": requirement["id"], "entity_type": "building", "entity_id": building["id"], "applicable_from": "2024-01-01"},
    )

    body = _ask(client, org_id, "Is this building's gas safety compliance up to date?", "building", building["id"])
    assert body["grounded"] is True
    assert len(body["tool_results"]) == 1
    assert body["tool_results"][0]["tool_name"] == "get_compliance_status"
    assert body["tool_results"][0]["records"][0]["requirement_id"] == requirement["id"]
    assert "compliance_status()" in body["answer_text"]
    assert len(body["suggested_follow_ups"]) > 0


def test_repeat_repairs_question_is_grounded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )

    body = _ask(client, org_id, "Have there been repeat repairs at this property?", "property", prop["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_repeat_repairs"
    assert result["records"][0]["repair_count"] == 3


def test_arrears_question_is_grounded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload(organisation_type="COMMERCIAL_LANDLORD")).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Unit 1"}).json()
    tenant = client.post("/api/v1/tenants", headers={"X-Organisation-Id": org_id}, json={"name": "Acme Retail Ltd"}).json()
    lease = client.post(
        "/api/v1/leases",
        headers={"X-Organisation-Id": org_id},
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 250000,
            "rent_frequency": "MONTHLY",
        },
    ).json()
    client.post(
        "/api/v1/rent-obligations",
        headers={"X-Organisation-Id": org_id},
        json={"lease_id": lease["id"], "obligation_type": "RENT", "due_date": "2026-01-01", "period_start": "2026-01-01", "period_end": "2026-01-31", "amount_due_pence": 100000},
    )

    body = _ask(client, org_id, "What are the arrears on this lease?", "lease", lease["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_arrears"
    assert result["records"][0]["outstanding_pence"] == 100000


def test_ungrounded_question_returns_fixed_message(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    body = _ask(client, org_id, "What's the weather like today?", "property", prop["id"])
    assert body["grounded"] is False
    assert body["tool_results"] == []
    assert "I don't have data" in body["answer_text"]


def test_question_matching_wrong_entity_type_is_ungrounded(client):
    """"Arrears" only applies to leases — asking about a property's
    arrears shouldn't accidentally match a different tool."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    body = _ask(client, org_id, "What are the arrears here?", "property", prop["id"])
    assert body["grounded"] is False


def test_defects_question_for_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={"category": "Windows", "description": "Water ingress", "reported_date": "2026-01-10", "building_id": building["id"]},
    )

    body = _ask(client, org_id, "Are there any open snagging defects on this building?", "building", building["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_defects"
    assert len(result["records"]) == 1
    assert result["records"][0]["category"] == "Windows"


def test_planned_investment_question_for_a_component_without_expected_life(client):
    """A component missing expected_life_years still returns a valid,
    grounded tool result — AGE_RATIO just comes back inapplicable,
    exactly like the direct planned-investment endpoint."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    component = client.post("/api/v1/components", headers={"X-Organisation-Id": org_id}, json={"component_type_id": boiler_type_id}).json()

    body = _ask(client, org_id, "Should we plan a replacement for this component?", "component", component["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_planned_investment"
    age_factor = next(f for f in result["records"][0]["factors"] if f["factor_code"] == "AGE_RATIO")
    assert age_factor["applicable"] is False


def test_property_360_question(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    body = _ask(client, org_id, "Give me a summary overview of this property.", "property", prop["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_property_360"
    assert result["records"][0]["address"] == "Flat 1"


def test_development_summary_question(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    development = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    building = client.post(
        "/api/v1/buildings",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Block A", "development_id": development["id"]},
    ).json()
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "building_id": building["id"]},
    )

    body = _ask(client, org_id, "Give me a summary overview of this development.", "development", development["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["tool_name"] == "get_development_summary"
    record = result["records"][0]
    assert record["buildings_count"] == 1
    assert record["properties_count"] == 1
    # A freshly created development is nowhere near handover-ready — no
    # canned "everything's fine" answer.
    assert record["handover_ready"] is False
    assert record["handover_readiness_score_pct"] < 100.0


def test_ask_requires_organisation_header(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.post("/api/v1/ask", json={"question": "test", "entity_type": "property", "entity_id": str(uuid.uuid4())})
    assert resp.status_code == 400


def test_ask_does_not_leak_another_organisations_data(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop_a = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_a}, json={"address": "Flat 1"}).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    # Authenticated against org B's own membership, asking about org A's
    # property_id: every tool filters by organisation_id == the caller's
    # own org, so this resolves to "not found" rather than leaking org
    # A's real data.
    body = _ask(client, signup_b["organisation_id"], "Give me an overview of this property.", "property", prop_a["id"])
    assert body["grounded"] is True
    result = body["tool_results"][0]
    assert result["records"] == []
    assert "not found" in result["calculation"]
