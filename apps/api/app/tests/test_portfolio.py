from datetime import date, timedelta


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


def test_portfolio_summary_empty_org(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get("/api/v1/portfolio/summary", headers={"X-Organisation-Id": signup["organisation_id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_properties"] == 0
    assert body["total_developments"] == 0
    assert body["total_components"] == 0
    assert body["properties_by_status"] == []
    assert body["open_defects_count"] == 0
    assert body["development_readiness"] == []


def test_portfolio_summary_aggregates_across_the_organisation(client):
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
    prop_a = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": dev["id"], "status": "OPERATIONAL"},
    ).json()
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 2", "development_id": dev["id"], "status": "UNDER_CONSTRUCTION"},
    )
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    client.post(
        "/api/v1/components",
        headers={"X-Organisation-Id": org_id},
        json={"component_type_id": boiler_type_id, "property_id": prop_a["id"]},
    )
    client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={
            "category": "Windows",
            "description": "Sticking window",
            "reported_date": "2020-01-01",
            "property_id": prop_a["id"],
            "target_date": "2020-01-15",  # long overdue, still OPEN
        },
    )
    soon = (date.today() + timedelta(days=30)).isoformat()
    client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={"provider": "A", "warranty_type": "x", "start_date": "2020-01-01", "expiry_date": soon},
    )

    resp = client.get("/api/v1/portfolio/summary", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_properties"] == 2
    assert body["total_developments"] == 1
    assert body["total_buildings"] == 1
    assert body["total_components"] == 1
    status_counts = {c["key"]: c["count"] for c in body["properties_by_status"]}
    assert status_counts == {"OPERATIONAL": 1, "UNDER_CONSTRUCTION": 1}
    assert body["open_defects_count"] == 1
    assert body["overdue_defects_count"] == 1
    assert body["warranties_expiring_within_90_days_count"] == 1
    assert len(body["development_readiness"]) == 1
    assert body["development_readiness"][0]["development_id"] == dev["id"]
    assert 0.0 <= body["development_readiness"][0]["score_pct"] <= 100.0


def test_portfolio_summary_isolates_by_organisation(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"address": "1 A St"}
    )

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get("/api/v1/portfolio/summary", headers={"X-Organisation-Id": signup_b["organisation_id"]})
    assert resp.status_code == 200
    assert resp.json()["total_properties"] == 0
