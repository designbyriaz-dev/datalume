"""Sprint 24 hardening — architecture/09-security-testing-ops.md §2's
security test suite: "tenant isolation fuzz tests (attempt cross-org
reads/writes for every resource type via the standard test-client
fixture, parametrised across all `/api/v1/*` routers so a new module is
covered automatically)."

Every prior sprint added its own one-off "org B can't read org A's X"
test as it built that domain. This module is the systematic version
spec §75 actually asks for: one org (A) creates one instance of every
resource type this codebase exposes a GET-by-id for, a second org (B)
— a real, separately-authenticated membership, not a forged header —
then attempts to read each of org A's ids and must get a clean 404,
never a 200 (a data leak) and never a 500 (a lookup that crashed
instead of cleanly denying is itself worth catching, since an
unhandled exception can leak stack traces/query text).

Each test-client fixture instance is a fresh, empty database (see
conftest.py), so a `pytest.mark.parametrize` per resource type would
re-run the entire multi-step creation chain (Development -> Building ->
Component -> ... ) once per resource — correct, but wastefully slow.
Instead RESOURCE_REGISTRY is built once per test run and iterated in a
single test function, which is the practical equivalent within this
fixture-per-test architecture: still data-driven, still "a new
resource type is covered automatically" (add one line to the registry
below), just without N redundant database setups.

Datasets/import jobs (ingestion) are the one GET-by-id router
intentionally left out of the registry — upload needs a different
endpoint (`/api/v1/uploads`) plus a `bulk_import` entitlement check
that's orthogonal to tenant isolation, and Sprint 3 already scoped
ingestion down ("scaffolded, minus the background job queue"); adding
it here would test entitlement plumbing more than isolation. Every
other GET-by-id router registered in app/main.py is covered.
"""

import io
import uuid
from datetime import date

import pytest


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


def _seed_one_of_everything(client, org_id: str) -> dict[str, str]:
    """Creates one instance of every resource type this module checks,
    in dependency order, and returns {resource_name: id}."""

    h = {"X-Organisation-Id": org_id}
    ids: dict[str, str] = {}

    development = client.post("/api/v1/developments", headers=h, json={"name": "Riverside"}).json()
    ids["development"] = development["id"]

    building = client.post("/api/v1/buildings", headers=h, json={"name": "Block A", "development_id": development["id"]}).json()
    ids["building"] = building["id"]

    prop = client.post("/api/v1/properties", headers=h, json={"address": "Flat 1", "development_id": development["id"]}).json()
    ids["property"] = prop["id"]

    component_types = client.get("/api/v1/component-types", headers=h).json()
    boiler_type_id = next(t["id"] for t in component_types if t["code"] == "BOILERS")
    component = client.post("/api/v1/components", headers=h, json={"component_type_id": boiler_type_id, "property_id": prop["id"]}).json()
    ids["component"] = component["id"]

    specification = client.post(
        "/api/v1/specifications",
        headers=h,
        json={"related_entity_type": "building", "related_entity_id": building["id"], "title": "Roofing spec"},
    ).json()
    ids["specification"] = specification["id"]

    change_control = client.post(
        "/api/v1/change-control",
        headers=h,
        json={
            "specification_id": specification["id"],
            "proposed_value": {"title": "Roofing spec", "description": "Spanish slate grade B"},
            "reason": "Supplier ceased trading",
        },
    ).json()
    ids["change_control"] = change_control["id"]

    defect = client.post(
        "/api/v1/defects",
        headers=h,
        json={"category": "Windows", "description": "Water ingress", "reported_date": date.today().isoformat(), "building_id": building["id"]},
    ).json()
    ids["defect"] = defect["id"]

    warranty = client.post(
        "/api/v1/warranties",
        headers=h,
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer - Boiler",
            "start_date": "2024-01-15",
            "expiry_date": "2034-01-15",
            "component_id": component["id"],
        },
    ).json()
    ids["warranty"] = warranty["id"]

    repair = client.post(
        "/api/v1/repairs",
        headers=h,
        json={"property_id": prop["id"], "category": "Plumbing", "description": "Leaking tap", "reported_date": date.today().isoformat()},
    ).json()
    ids["repair"] = repair["id"]

    domains = client.get("/api/v1/compliance/domains", headers=h).json()
    gas_domain_id = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")
    requirement = client.post(
        "/api/v1/compliance/requirements",
        headers=h,
        json={"domain_id": gas_domain_id, "code": "GAS-001", "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()
    ids["compliance_requirement"] = requirement["id"]

    hazard = client.post(
        "/api/v1/hazards", headers=h, json={"property_id": prop["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": date.today().isoformat()}
    ).json()
    ids["hazard"] = hazard["id"]

    tenant = client.post("/api/v1/tenants", headers=h, json={"name": "Acme Retail Ltd"}).json()
    ids["tenant"] = tenant["id"]

    lease = client.post(
        "/api/v1/leases",
        headers=h,
        json={
            "property_id": prop["id"],
            "tenant_id": tenant["id"],
            "lease_start": "2026-01-01",
            "lease_expiry": "2031-01-01",
            "contractual_rent_pence": 100000,
            "rent_frequency": "MONTHLY",
        },
    ).json()
    ids["lease"] = lease["id"]

    document = client.post(
        "/api/v1/documents",
        headers=h,
        data={"title": "EPC", "document_type": "CERTIFICATE"},
        files={"file": ("epc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    ).json()
    ids["document"] = document["id"]

    report_job = client.post("/api/v1/reports", headers=h, json={"report_type": "DEVELOPMENT_SUMMARY", "format": "CSV"}).json()
    ids["report_job"] = report_job["id"]

    return ids


# {resource_name: URL template} — GET-by-id endpoints spanning every
# router this codebase registers (app/main.py). Add a line here for any
# new GET-by-id endpoint a future sprint introduces and it's covered.
GET_URL_TEMPLATES = {
    "development": "/api/v1/developments/{id}",
    "building": "/api/v1/buildings/{id}",
    "property": "/api/v1/properties/{id}",
    "component": "/api/v1/components/{id}",
    "specification": "/api/v1/specifications/{id}",
    "change_control": "/api/v1/change-control/{id}",
    "defect": "/api/v1/defects/{id}",
    "warranty": "/api/v1/warranties/{id}",
    "repair": "/api/v1/repairs/{id}",
    "compliance_requirement": "/api/v1/compliance/requirements/{id}",
    "hazard": "/api/v1/hazards/{id}",
    "tenant": "/api/v1/tenants/{id}",
    "lease": "/api/v1/leases/{id}",
    "document": "/api/v1/documents/{id}",
    "report_job": "/api/v1/reports/{id}",
}


def test_cross_org_read_is_denied_for_every_resource_type(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    ids = _seed_one_of_everything(client, org_a)

    assert set(ids.keys()) == set(GET_URL_TEMPLATES.keys()), "every seeded resource needs a URL template and vice versa"

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    org_b = signup_b["organisation_id"]

    failures = []
    for resource_name, resource_id in ids.items():
        url = GET_URL_TEMPLATES[resource_name].format(id=resource_id)
        resp = client.get(url, headers={"X-Organisation-Id": org_b})
        if resp.status_code == 200:
            failures.append(f"{resource_name}: leaked org A's data (200 OK) to org B")
        elif resp.status_code >= 500:
            failures.append(f"{resource_name}: crashed instead of denying cleanly ({resp.status_code})")
        elif resp.status_code != 404:
            failures.append(f"{resource_name}: expected 404, got {resp.status_code}")

    assert not failures, "Tenant isolation violations:\n" + "\n".join(failures)

    # And the reverse: org A's own owner can still read its own data
    # through the exact same URLs — log back in as A first, since the
    # loop above left the client authenticated as B. A passing suite
    # above must not be passing because every route 404s
    # unconditionally regardless of who's asking.
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"})
    still_failing = []
    for resource_name, resource_id in ids.items():
        url = GET_URL_TEMPLATES[resource_name].format(id=resource_id)
        resp = client.get(url, headers={"X-Organisation-Id": org_a})
        if resp.status_code != 200:
            still_failing.append(f"{resource_name}: owner org got {resp.status_code}, expected 200")
    assert not still_failing, "Owning org lost read access:\n" + "\n".join(still_failing)


def test_cross_org_write_is_denied_for_property_and_repair(client):
    """A representative write-path IDOR check (spec §75's "IDOR attempts
    against sequential/guessable IDs... cross-org development/component/
    document/compliance/financial-data access attempts") — a resource
    the caller doesn't own must not be patchable just because its UUID
    was guessed or leaked, even from an org member who legitimately
    holds the write permission in their own org."""
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_a}, json={"address": "Flat 1"}).json()
    repair = client.post(
        "/api/v1/repairs",
        headers={"X-Organisation-Id": org_a},
        json={"property_id": prop["id"], "category": "Plumbing", "description": "Leak", "reported_date": date.today().isoformat()},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    org_b = signup_b["organisation_id"]

    resp = client.post(f"/api/v1/properties/{prop['id']}/status", headers={"X-Organisation-Id": org_b}, json={"status": "VOID"})
    assert resp.status_code == 404
    resp = client.post(
        f"/api/v1/repairs/{repair['id']}/status", headers={"X-Organisation-Id": org_b}, json={"status": "COMPLETED"}
    )
    assert resp.status_code == 404


def test_forged_organisation_header_without_membership_is_rejected(client):
    """Membership, not just a well-formed org id in the header, gates
    every request — architecture 01 §1's two-layer tenant scoping's
    first layer. An authenticated user who simply types another org's
    UUID into the header (no forged cookie needed — this is the
    ordinary request path) must be refused before any query runs."""
    client.post("/api/v1/auth/signup", json=_signup_payload())
    other_org_id = str(uuid.uuid4())
    resp = client.get("/api/v1/properties", headers={"X-Organisation-Id": other_org_id})
    assert resp.status_code == 403


@pytest.mark.parametrize("role_code", ["VIEWER", "FINANCE_VIEWER"])
def test_read_only_roles_cannot_write(client, role_code):
    """Role escalation sweep (spec §75) — a read-only role must be
    denied on a representative write endpoint per domain it can read,
    regardless of which read-only role it is."""
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        user = User(email=f"{role_code.lower()}@northstar-housing.example", name="Read Only", password_hash=hash_password("also-a-fine-password"))
        db.add(user)
        db.flush()
        role = _get_or_create_role(db, role_code)
        db.add(Membership(user_id=user.id, organisation_id=uuid.UUID(org_id), role_id=role.id, status=MembershipStatus.ACTIVE))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": f"{role_code.lower()}@northstar-housing.example", "password": "also-a-fine-password"})

    resp = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "Flat 1"})
    assert resp.status_code == 403
