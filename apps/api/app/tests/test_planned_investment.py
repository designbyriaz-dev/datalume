"""Planned Investment — architecture/03-development-domain.md §6, spec
§40: "do not use age alone." Each test isolates one factor or the
overall weighted composition."""

import uuid
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


def _boiler_component(client, org_id, **overrides):
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    payload = {"component_type_id": boiler_type_id}
    payload.update(overrides)
    return client.post("/api/v1/components", headers={"X-Organisation-Id": org_id}, json=payload).json()


def _gas_safety_domain_id(client, org_id):
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    return next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")


def _gas_requirement(client, org_id):
    domain_id = _gas_safety_domain_id(client, org_id)
    return client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()


def _score(client, org_id, component_id):
    resp = client.get(f"/api/v1/components/{component_id}/planned-investment", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _factor(body, code):
    return next(f for f in body["factors"] if f["factor_code"] == code)


def test_component_without_expected_life_is_excluded_from_the_portfolio_list(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _boiler_component(client, org_id, installation_date="2020-01-01")  # no expected_life_years

    resp = client.get("/api/v1/planned-investment", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert resp.json() == []


def test_component_with_only_age_known_scores_using_applicable_factors_only(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    ten_years_ago = (date.today() - timedelta(days=365 * 10)).isoformat()
    component = _boiler_component(client, org_id, installation_date=ten_years_ago, expected_life_years=20)

    body = _score(client, org_id, component["id"])
    age_factor = _factor(body, "AGE_RATIO")
    assert age_factor["applicable"] is True
    assert 0.45 <= age_factor["value"] <= 0.55

    condition_factor = _factor(body, "CONDITION_SIGNAL")
    assert condition_factor["applicable"] is False
    assert condition_factor["value"] is None

    repair_factor = _factor(body, "REPAIR_FREQUENCY")
    assert repair_factor["applicable"] is True
    assert repair_factor["value"] == 0.0

    failure_factor = _factor(body, "FAILURE_PATTERN")
    assert failure_factor["value"] == 0.0

    compliance_factor = _factor(body, "COMPLIANCE_LINKED")
    assert compliance_factor["value"] == 0.0

    # Only AGE_RATIO, REPAIR_FREQUENCY, FAILURE_PATTERN, COMPLIANCE_LINKED
    # are applicable; all but AGE_RATIO are 0, so the score is roughly
    # AGE_RATIO's own ~0.5 value scaled by its share of applicable weight,
    # not simply 50 — just confirm it's a real, non-trivial, non-zero score.
    assert 0 < body["priority_score"] < 50


def test_condition_signal_from_component_level_inspection(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    component = _boiler_component(client, org_id)
    requirement = _gas_requirement(client, org_id)
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "component",
            "entity_id": component["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2026-01-01",
            "result": "UNSATISFACTORY",
        },
    )

    body = _score(client, org_id, component["id"])
    condition_factor = _factor(body, "CONDITION_SIGNAL")
    assert condition_factor["applicable"] is True
    assert condition_factor["value"] == 1.0


def test_compliance_linked_from_open_action(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    component = _boiler_component(client, org_id)
    requirement = _gas_requirement(client, org_id)
    client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "component",
            "entity_id": component["id"],
            "description": "Replace part",
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
        },
    )

    body = _score(client, org_id, component["id"])
    compliance_factor = _factor(body, "COMPLIANCE_LINKED")
    assert compliance_factor["value"] == 1.0


def test_repair_frequency_and_failure_pattern_from_repairs(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    component = _boiler_component(client, org_id, property_id=prop["id"])

    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={
                "property_id": prop["id"],
                "component_id": component["id"],
                "category": "Heating",
                "description": "Boiler fault",
                "reported_date": date.today().isoformat(),
            },
        )

    body = _score(client, org_id, component["id"])
    repair_factor = _factor(body, "REPAIR_FREQUENCY")
    assert repair_factor["value"] == 1.0  # 3 repairs, default threshold 3 -> min(3/3, 1.0)

    failure_factor = _factor(body, "FAILURE_PATTERN")
    assert failure_factor["value"] == 1.0  # default REPEAT_FAILURES_PER_COMPONENT threshold is also 3


def test_raising_a_factor_weight_increases_its_contribution(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    component = _boiler_component(client, org_id, property_id=prop["id"])
    requirement = _gas_requirement(client, org_id)
    client.post(
        "/api/v1/compliance/actions",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "component",
            "entity_id": component["id"],
            "description": "Replace part",
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
        },
    )

    before = _score(client, org_id, component["id"])["priority_score"]

    resp = client.patch(
        "/api/v1/planned-investment-weights/COMPLIANCE_LINKED",
        headers={"X-Organisation-Id": org_id},
        json={"weight": 5.0},
    )
    assert resp.status_code == 200

    after = _score(client, org_id, component["id"])["priority_score"]
    assert after > before


def test_planned_investment_list_sorted_descending_and_filterable(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building = client.post("/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}).json()
    other_building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}
    ).json()

    old = (date.today() - timedelta(days=365 * 19)).isoformat()
    new = (date.today() - timedelta(days=30)).isoformat()
    old_component = _boiler_component(
        client, org_id, building_id=building["id"], installation_date=old, expected_life_years=20
    )
    _boiler_component(client, org_id, building_id=building["id"], installation_date=new, expected_life_years=20)
    _boiler_component(client, org_id, building_id=other_building["id"], installation_date=old, expected_life_years=20)

    resp = client.get(
        "/api/v1/planned-investment", headers={"X-Organisation-Id": org_id}, params={"building_id": building["id"]}
    )
    assert resp.status_code == 200
    scores = resp.json()
    assert len(scores) == 2
    assert scores[0]["priority_score"] >= scores[1]["priority_score"]
    assert scores[0]["component_id"] == old_component["id"]


def test_planned_investment_component_not_found_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.get(
        f"/api/v1/components/{uuid.uuid4()}/planned-investment", headers={"X-Organisation-Id": org_id}
    )
    assert resp.status_code == 404


def test_weight_write_requires_development_write_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-housing.example",
            name="Repairs Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "REPAIRS_MANAGER")
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
    resp = client.patch(
        "/api/v1/planned-investment-weights/AGE_RATIO", headers={"X-Organisation-Id": org_id}, json={"weight": 0.9}
    )
    assert resp.status_code == 403
