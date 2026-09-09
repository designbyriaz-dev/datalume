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


def test_compliance_domains_catalog_is_seeded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    codes = {d["code"] for d in resp.json()}
    assert len(codes) == 21
    assert {"GAS_SAFETY", "FIRE_SAFETY", "ASBESTOS_MANAGEMENT", "DAMP_AND_MOULD"} <= codes
    assert all(d["organisation_id"] is None for d in resp.json())  # all global at this point


def test_compliance_frameworks_seeded(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get("/api/v1/compliance/frameworks", headers={"X-Organisation-Id": signup["organisation_id"]})
    assert resp.status_code == 200
    frameworks = resp.json()
    assert len(frameworks) == 1
    assert frameworks[0]["name"] == "DataLume Compliance Framework"
    assert frameworks[0]["organisation_id"] is None


def _gas_safety_domain_id(client, org_id):
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    return next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")


def test_add_org_specific_domain(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.post(
        "/api/v1/compliance/domains",
        headers={"X-Organisation-Id": org_id},
        json={"code": "COMMERCIAL_EICR", "name": "EICR — commercial units", "description": "Commercial unit wiring checks"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["organisation_id"] == org_id

    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    assert any(d["code"] == "COMMERCIAL_EICR" and d["organisation_id"] == org_id for d in domains)
    assert len(domains) == 22  # 21 global + 1 org-specific


def test_add_requirement_against_a_domain(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)

    resp = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={
            "domain_id": domain_id,
            "code": "GAS-001",
            "title": "Annual gas safety check",
            "description": "Landlord Gas Safety Record for all gas appliances",
            "cadence": "annual",
            "effective_date": "2024-01-01",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 1
    assert body["superseded_date"] is None
    assert body["organisation_id"] == org_id


def test_duplicate_requirement_code_in_the_same_domain_is_rejected(client):
    """Regression test: caught during Sprint 15's own live verification —
    creating a second top-level requirement with a code that already
    exists (current, non-superseded) in the same domain would silently
    corrupt the version-lineage lookup, which matches on (domain_id,
    code) rather than a separate lineage_id column. The fix is a new
    version of the existing requirement, not a second create."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    )

    resp = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "A different requirement", "effective_date": "2024-01-01"},
    )
    assert resp.status_code == 400

    # The same code in a *different* domain is fine — codes are scoped
    # to (organisation_id, domain_id), not globally unique.
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    fire_domain_id = next(d["id"] for d in domains if d["code"] == "FIRE_SAFETY")
    other_domain_resp = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": fire_domain_id, "code": "GAS-001", "title": "Coincidentally same code", "effective_date": "2024-01-01"},
    )
    assert other_domain_resp.status_code == 201


def test_requirement_against_missing_domain_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "domain_id": str(uuid.uuid4()),
            "code": "GAS-001",
            "title": "x",
            "effective_date": "2024-01-01",
        },
    )
    assert resp.status_code == 404


def test_requirement_versioning_supersedes_previous_and_keeps_code(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    original = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={
            "domain_id": domain_id,
            "code": "GAS-001",
            "title": "Annual gas safety check",
            "cadence": "annual",
            "effective_date": "2024-01-01",
        },
    ).json()

    revised = client.post(
        f"/api/v1/compliance/requirements/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"cadence": "annual, within 12 months of previous check", "effective_date": "2025-06-01"},
    )
    assert revised.status_code == 201
    revised_body = revised.json()
    assert revised_body["code"] == "GAS-001"
    assert revised_body["version"] == 2
    assert revised_body["title"] == "Annual gas safety check"  # carried forward, not re-supplied
    assert revised_body["cadence"] == "annual, within 12 months of previous check"

    old = client.get(f"/api/v1/compliance/requirements/{original['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert old["superseded_date"] == "2025-06-01"
    assert len(old["versions"]) == 2
    assert [v["version"] for v in old["versions"]] == [1, 2]

    current_list = client.get(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        params={"domain_id": domain_id},
    ).json()
    assert len(current_list) == 1
    assert current_list[0]["version"] == 2


def test_cannot_version_an_already_superseded_requirement(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    original = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()
    client.post(
        f"/api/v1/compliance/requirements/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"effective_date": "2025-01-01"},
    )

    resp = client.post(
        f"/api/v1/compliance/requirements/{original['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"effective_date": "2026-01-01"},
    )
    assert resp.status_code == 400


def test_add_applicability_against_a_building(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()

    resp = client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": "2024-01-01",
            "basis": "Communal gas installation present",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["entity_type"] == "building"
    assert body["entity_id"] == building["id"]
    assert body["applicable_to"] is None


def test_applicability_against_unsupported_entity_type_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()

    resp = client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "development",
            "entity_id": str(uuid.uuid4()),
            "applicable_from": "2024-01-01",
        },
    )
    assert resp.status_code == 400


def test_applicability_against_missing_building_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()

    resp = client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": str(uuid.uuid4()),
            "applicable_from": "2024-01-01",
        },
    )
    assert resp.status_code == 404


def test_end_applicability(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    applicability = client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "applicable_from": "2024-01-01",
        },
    ).json()

    resp = client.post(
        f"/api/v1/compliance/applicability/{applicability['id']}/end",
        headers={"X-Organisation-Id": org_id},
        json={"applicable_to": "2026-01-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["applicable_to"] == "2026-01-01"


def test_list_applicability_filters_by_entity(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()
    building_a = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    building_b = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block B"}
    ).json()
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building_a["id"],
            "applicable_from": "2024-01-01",
        },
    )
    client.post(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building_b["id"],
            "applicable_from": "2024-01-01",
        },
    )

    resp = client.get(
        "/api/v1/compliance/applicability",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "building", "entity_id": building_a["id"]},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["entity_id"] == building_a["id"]


def test_compliance_write_requires_operations_compliance_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_id)

    db = db_module.SessionLocal()
    try:
        # REPAIRS_MANAGER has operations.write but not operations.compliance —
        # the narrower permission this whole module is gated behind.
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
    resp = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    )
    assert resp.status_code == 403


def test_compliance_requirement_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    domain_id = _gas_safety_domain_id(client, org_a)
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_a},
        json={"domain_id": domain_id, "code": "GAS-001", "title": "x", "effective_date": "2024-01-01"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/compliance/requirements/{requirement['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
