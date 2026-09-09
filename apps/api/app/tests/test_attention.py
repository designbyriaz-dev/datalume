"""Cross-Domain Attention Engine — architecture/06-intelligence-layer.md
§3. Each test isolates one rule's own cross-domain composition, plus
the upsert/dismissal semantics that make attention_scan.py idempotent."""

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


def _scan(client, org_id):
    resp = client.post("/api/v1/attention/scan", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _signals(client, org_id, **params):
    resp = client.get("/api/v1/attention/signals", headers={"X-Organisation-Id": org_id}, params=params)
    assert resp.status_code == 200
    return resp.json()


def test_rules_are_lazily_seeded_with_four_defaults(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.get("/api/v1/attention/rules", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    codes = {r["code"] for r in resp.json()}
    assert codes == {"WARRANTY_EXPIRING_WITH_OPEN_DEFECT", "REPEAT_FAILURE", "COMPLIANCE_BREACH", "LEASE_ARREARS"}
    assert all(r["is_active"] for r in resp.json())


def test_warranty_expiring_with_open_defect_rule(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    component = _boiler_component(client, org_id)

    client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
            "component_id": component["id"],
        },
    )
    client.post(
        "/api/v1/defects",
        headers={"X-Organisation-Id": org_id},
        json={
            "category": "Heating",
            "description": "Boiler fault",
            "reported_date": date.today().isoformat(),
            "component_id": component["id"],
        },
    )

    result = _scan(client, org_id)
    assert result["signals_created"] >= 1

    signals = _signals(client, org_id, entity_type="warranty")
    assert len(signals) == 1
    assert signals[0]["explanation"]["what"]
    assert signals[0]["explanation"]["why"]
    assert signals[0]["explanation"]["supporting_record_ids"]
    assert signals[0]["explanation"]["recommended_investigation"]


def test_warranty_without_open_defect_does_not_trigger(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    component = _boiler_component(client, org_id)
    client.post(
        "/api/v1/warranties",
        headers={"X-Organisation-Id": org_id},
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer",
            "start_date": "2024-01-15",
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
            "component_id": component["id"],
        },
    )

    _scan(client, org_id)
    assert _signals(client, org_id, entity_type="warranty") == []


def test_repeat_failure_rule(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()

    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )

    result = _scan(client, org_id)
    assert result["signals_created"] >= 1

    signals = _signals(client, org_id, entity_type="property")
    assert len(signals) == 1
    assert signals[0]["entity_id"] == prop["id"]


def test_compliance_breach_rule(client):
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
    client.post(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        json={
            "requirement_id": requirement["id"],
            "entity_type": "building",
            "entity_id": building["id"],
            "inspector": "Gas Safe Ltd",
            "inspection_date": "2025-01-01",
            "result": "SATISFACTORY",
            "next_due_date": (date.today() - timedelta(days=5)).isoformat(),
        },
    )

    result = _scan(client, org_id)
    assert result["signals_created"] >= 1

    signals = _signals(client, org_id, entity_type="building")
    assert len(signals) == 1
    assert signals[0]["entity_id"] == building["id"]
    assert "GAS-001" in signals[0]["explanation"]["what"]


def test_lease_arrears_rule(client):
    signup = client.post(
        "/api/v1/auth/signup", json=_signup_payload(organisation_type="COMMERCIAL_LANDLORD")
    ).json()
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
    client.post(f"/api/v1/leases/{lease['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "ACTIVE"})
    client.post(
        "/api/v1/rent-obligations",
        headers={"X-Organisation-Id": org_id},
        json={
            "lease_id": lease["id"],
            "obligation_type": "RENT",
            "due_date": "2026-01-01",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "amount_due_pence": 250000,  # above the default 50000-pence threshold
        },
    )

    result = _scan(client, org_id)
    assert result["signals_created"] >= 1

    signals = _signals(client, org_id, entity_type="lease")
    assert len(signals) == 1
    assert signals[0]["entity_id"] == lease["id"]


def test_rescanning_refreshes_open_signal_instead_of_duplicating(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )

    first = _scan(client, org_id)
    assert first["signals_created"] == 1

    second = _scan(client, org_id)
    assert second["signals_created"] == 0
    assert second["signals_refreshed"] == 1

    signals = _signals(client, org_id, entity_type="property")
    assert len(signals) == 1  # still exactly one row, not two


def test_dismissed_signal_is_not_recreated_by_a_later_scan(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )
    _scan(client, org_id)
    signal = _signals(client, org_id, entity_type="property")[0]

    resp = client.post(
        f"/api/v1/attention/signals/{signal['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "DISMISSED"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISMISSED"

    _scan(client, org_id)
    open_signals = _signals(client, org_id, entity_type="property", signal_status="OPEN")
    assert open_signals == []
    dismissed_signals = _signals(client, org_id, entity_type="property", signal_status="DISMISSED")
    assert len(dismissed_signals) == 1


def test_resolved_signal_gets_a_fresh_row_if_condition_recurs(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )
    _scan(client, org_id)
    signal = _signals(client, org_id, entity_type="property")[0]
    client.post(
        f"/api/v1/attention/signals/{signal['id']}/status", headers={"X-Organisation-Id": org_id}, json={"status": "RESOLVED"}
    )

    result = _scan(client, org_id)
    assert result["signals_created"] == 1  # a genuinely new occurrence, not a duplicate of the resolved one

    all_signals = _signals(client, org_id, entity_type="property")
    assert len(all_signals) == 2
    assert {s["status"] for s in all_signals} == {"RESOLVED", "OPEN"}


def test_deactivating_a_rule_stops_it_from_firing(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_id},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )

    rules = client.get("/api/v1/attention/rules", headers={"X-Organisation-Id": org_id}).json()
    repeat_failure_rule = next(r for r in rules if r["code"] == "REPEAT_FAILURE")
    resp = client.patch(
        f"/api/v1/attention/rules/{repeat_failure_rule['id']}", headers={"X-Organisation-Id": org_id}, json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    result = _scan(client, org_id)
    assert result["rules_evaluated"] == 3  # 4 default rules minus the one just disabled
    assert _signals(client, org_id, entity_type="property") == []


def test_signals_require_an_organisation_header(client):
    """reports.read (signal viewing/triage) is held by every role in
    this build's RBAC table today — there's no role to prove a genuine
    403 boundary against, so this test covers the one real
    precondition that does apply: an authenticated request with no
    X-Organisation-Id still can't see anything."""
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.get("/api/v1/attention/signals")
    assert resp.status_code == 400


def test_scan_and_rule_updates_require_reports_board_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        user = User(email="manager@northstar-housing.example", name="Manager", password_hash=hash_password("also-a-fine-password"))
        db.add(user)
        db.flush()
        # MANAGER has reports.read but not reports.board.
        role = _get_or_create_role(db, "MANAGER")
        db.add(Membership(user_id=user.id, organisation_id=uuid.UUID(org_id), role_id=role.id, status=MembershipStatus.ACTIVE))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "manager@northstar-housing.example", "password": "also-a-fine-password"})
    resp = client.post("/api/v1/attention/scan", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 403


def test_signal_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_a}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_a},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )
    _scan(client, org_a)
    signal = _signals(client, org_a, entity_type="property")[0]

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.post(
        f"/api/v1/attention/signals/{signal['id']}/status",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
        json={"status": "ACKNOWLEDGED"},
    )
    assert resp.status_code == 404


def test_worker_multi_org_scan_stays_isolated_per_organisation(client):
    """run_attention_scan_for_all_organisations is the function
    app/worker/main.py's nightly loop actually calls — the router's
    /scan endpoint (every other test above) only exercises the
    single-org path. This is the one test that drives the multi-org
    entrypoint directly, confirming it commits per-org and doesn't
    leak one org's signals into another's."""
    import app.core.db as db_module
    from app.worker.jobs.attention_scan import run_attention_scan_for_all_organisations

    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_a}, json={"address": "Flat 1"}).json()
    for _ in range(3):
        client.post(
            "/api/v1/repairs",
            headers={"X-Organisation-Id": org_a},
            json={"property_id": prop["id"], "category": "Plumbing", "description": "x", "reported_date": date.today().isoformat()},
        )

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    org_b = signup_b["organisation_id"]

    db = db_module.SessionLocal()
    try:
        results = run_attention_scan_for_all_organisations(db)
    finally:
        db.close()

    assert uuid.UUID(org_a) in results
    assert uuid.UUID(org_b) in results
    assert results[uuid.UUID(org_a)].signals_created == 1  # the repeat-repair pattern
    assert results[uuid.UUID(org_b)].signals_created == 0  # nothing recorded for org B

    # Re-authenticate as org B's own user to confirm nothing leaked in.
    signals_b = _signals(client, org_b, entity_type="property")
    assert signals_b == []

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"})
    signals_a = _signals(client, org_a, entity_type="property")
    assert len(signals_a) == 1
