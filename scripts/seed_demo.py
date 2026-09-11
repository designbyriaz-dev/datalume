"""Seed the two fictional demo organisations named in
architecture/00-executive-architecture.md's own repo layout comment:
Northstar Housing (a housing association) and Northstar Commercial (a
commercial landlord) — Sprint 24's "Northstar demo data complete" line.

All data created here is fictional/synthetic, per spec §70.

**Scale**: an earlier version of this docstring (Sprint 1) sketched a
much larger dataset ("~12,480 operational properties") as a directional
placeholder — architecture itself never mandates a specific scale, only
that the two named orgs exist with representative data. What actually
makes a demo useful is *variety* (a development mid-handover next to a
finished one; a compliant building next to an overdue one; a lease in
arrears next to one that's current) so every domain built across all 24
sprints has something real to show, not raw row count. This seeds
dozens of records per org, not thousands — enough to click through
every page and see the engines (handover readiness, repeat repairs,
compliance status, attention signals, arrears) produce genuinely
different results across records, in seconds rather than minutes.

**Idempotency**: organisation/user/membership are upserted by
slug/email, matching Sprint 1's original behaviour, so re-running this
against a persistent database never duplicates logins. The domain data
below it is coarser-grained idempotent: if an org already has any
developments (Housing) or any leases (Commercial), that org's domain
data is assumed already seeded and is skipped entirely, rather than
tracking per-row dedup for every one of the ~15 resource types created
below — documented here rather than silently under- or over-seeding.

This script drives the real FastAPI app in-process via Starlette's
TestClient (the same mechanism app/tests/conftest.py uses for every
test in this codebase) rather than hand-reconstructing every service
function's exact keyword arguments — every payload below is the same
shape already verified against the real API by this codebase's own
test suite, so seeding exercises the real validation/permission/
service-call path end-to-end instead of writing rows directly.

Usage (from apps/api, with the venv active and DATABASE_URL/REDIS_URL
pointed at a running Postgres/Redis):

    python ../../scripts/seed_demo.py
"""

from datetime import date, timedelta

from starlette.testclient import TestClient

from app.auth.models import Membership, MembershipStatus, Role, User
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.organisations.models import Organisation, OrganisationType, Workspace

HOUSING_OWNER_EMAIL = "demo-owner@northstar-housing.example"
COMMERCIAL_OWNER_EMAIL = "demo-owner@northstar-commercial.example"
DEMO_PASSWORD = "northstar-demo-2026"  # local/demo only — never used outside seeded environments

TODAY = date.today()


def get_or_create_role(db, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code, Role.organisation_id.is_(None)).first()
    if role is None:
        role = Role(code=code, name=code.replace("_", " ").title(), organisation_id=None)
        db.add(role)
        db.flush()
    return role


def ensure_org_and_owner(db, *, slug: str, name: str, org_type: OrganisationType, goals: list[str], owner_email: str, owner_name: str) -> tuple[Organisation, bool]:
    org = db.query(Organisation).filter(Organisation.slug == slug).first()
    created = org is None
    if org is None:
        org = Organisation(name=name, slug=slug, organisation_type=org_type, goals=goals)
        db.add(org)
        db.flush()
        db.add(Workspace(organisation_id=org.id, name="Default Workspace", workspace_type="DEFAULT"))
        print(f"Created organisation {org.name} ({org.slug})")
    else:
        print(f"Organisation {org.slug} already exists, reusing")

    user = db.query(User).filter(User.email == owner_email).first()
    if user is None:
        user = User(email=owner_email, name=owner_name, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
        print(f"Created demo login {owner_email} / {DEMO_PASSWORD}")
    else:
        print(f"User {owner_email} already exists, reusing")

    existing_membership = db.query(Membership).filter(Membership.user_id == user.id, Membership.organisation_id == org.id).first()
    if existing_membership is None:
        owner_role = get_or_create_role(db, "OWNER")
        db.add(Membership(user_id=user.id, organisation_id=org.id, role_id=owner_role.id, status=MembershipStatus.ACTIVE))
        print(f"Granted OWNER membership on {slug}")

    db.commit()
    return org, created


def _login(client: TestClient, email: str) -> None:
    client.cookies.clear()
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    resp.raise_for_status()


def seed_housing_domain_data(client: TestClient, org_id: str) -> None:
    h = {"X-Organisation-Id": org_id}

    if client.get("/api/v1/developments", headers=h).json():
        print("Northstar Housing already has developments — skipping domain data seed")
        return

    riverside = client.post("/api/v1/developments", headers=h, json={"name": "Riverside Gardens", "address": "Riverside Way, Manchester"}).json()
    elm_grove = client.post("/api/v1/developments", headers=h, json={"name": "Elm Grove Extension", "address": "Elm Grove, Manchester"}).json()

    riverside_house = client.post("/api/v1/buildings", headers=h, json={"name": "Riverside House", "development_id": riverside["id"], "storeys": 4}).json()
    willow_court = client.post("/api/v1/buildings", headers=h, json={"name": "Willow Court", "development_id": riverside["id"], "storeys": 3}).json()
    elm_court = client.post("/api/v1/buildings", headers=h, json={"name": "Elm Court", "development_id": elm_grove["id"], "storeys": 2}).json()

    riverside_properties = [
        client.post("/api/v1/properties", headers=h, json={"address": f"Flat {n}, Riverside House", "development_id": riverside["id"], "building_id": riverside_house["id"], "status": "OPERATIONAL"}).json()
        for n in range(1, 4)
    ] + [
        client.post("/api/v1/properties", headers=h, json={"address": f"Flat {n}, Willow Court", "development_id": riverside["id"], "building_id": willow_court["id"], "status": "OPERATIONAL"}).json()
        for n in range(1, 4)
    ]
    elm_properties = [
        client.post("/api/v1/properties", headers=h, json={"address": f"Flat {n}, Elm Court", "development_id": elm_grove["id"], "building_id": elm_court["id"], "status": "UNDER_CONSTRUCTION"}).json()
        for n in range(1, 3)
    ]

    component_types = client.get("/api/v1/component-types", headers=h).json()
    boiler_type_id = next(t["id"] for t in component_types if t["code"] == "BOILERS")
    door_type_id = next(t["id"] for t in component_types if t["code"] == "EXTERNAL_DOORS")

    boiler_components = [
        client.post("/api/v1/components", headers=h, json={"component_type_id": boiler_type_id, "property_id": p["id"], "installation_date": "2023-06-01"}).json()
        for p in riverside_properties
    ]
    client.post("/api/v1/components", headers=h, json={"component_type_id": door_type_id, "property_id": elm_properties[0]["id"]})

    spec = client.post(
        "/api/v1/specifications",
        headers=h,
        json={"related_entity_type": "building", "related_entity_id": riverside_house["id"], "title": "Roofing specification", "effective_date": "2023-01-01"},
    ).json()
    client.post(
        "/api/v1/change-control",
        headers=h,
        json={
            "specification_id": spec["id"],
            "proposed_value": {"title": "Roofing specification", "description": "Spanish slate grade B"},
            "reason": "Original Welsh slate supplier ceased trading",
            "impact_description": "No programme impact",
        },
    )

    client.post(
        "/api/v1/defects",
        headers=h,
        json={"category": "Windows", "description": "Water ingress around frame", "reported_date": (TODAY - timedelta(days=10)).isoformat(), "building_id": riverside_house["id"], "severity": "HIGH"},
    )
    completed_defect = client.post(
        "/api/v1/defects",
        headers=h,
        json={"category": "Plumbing", "description": "Dripping tap in communal area", "reported_date": (TODAY - timedelta(days=60)).isoformat(), "building_id": willow_court["id"]},
    ).json()
    client.post(f"/api/v1/defects/{completed_defect['id']}/status", headers=h, json={"status": "COMPLETED", "completion_date": (TODAY - timedelta(days=40)).isoformat()})
    client.post(
        "/api/v1/defects",
        headers=h,
        json={"category": "Render", "description": "Cracking to external render", "reported_date": (TODAY - timedelta(days=5)).isoformat(), "building_id": elm_court["id"]},
    )

    client.post(
        "/api/v1/warranties",
        headers=h,
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer - Boiler",
            "start_date": "2023-06-01",
            "expiry_date": (TODAY + timedelta(days=45)).isoformat(),  # expiring soon — feeds the Attention Engine
            "component_id": boiler_components[0]["id"],
        },
    )
    client.post(
        "/api/v1/warranties",
        headers=h,
        json={
            "provider": "Worcester Bosch",
            "warranty_type": "Manufacturer - Boiler",
            "start_date": "2023-06-01",
            "expiry_date": "2033-06-01",
            "component_id": boiler_components[1]["id"],
        },
    )

    # Four Plumbing repairs on the same property trips the repeat-repair
    # engine's threshold; two more elsewhere are ordinary, isolated repairs.
    for i in range(4):
        client.post(
            "/api/v1/repairs",
            headers=h,
            json={"property_id": riverside_properties[0]["id"], "category": "Plumbing", "description": f"Leak report #{i + 1}", "reported_date": (TODAY - timedelta(days=30 - i * 7)).isoformat()},
        )
    client.post("/api/v1/repairs", headers=h, json={"property_id": riverside_properties[3]["id"], "category": "Electrical", "description": "Flickering hallway light", "reported_date": (TODAY - timedelta(days=3)).isoformat()})
    client.post("/api/v1/repairs", headers=h, json={"property_id": elm_properties[0]["id"], "category": "Heating", "description": "No hot water", "reported_date": (TODAY - timedelta(days=1)).isoformat(), "priority": "URGENT"})

    domains = client.get("/api/v1/compliance/domains", headers=h).json()
    gas_domain_id = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")
    gas_requirement = client.post(
        "/api/v1/compliance/requirements",
        headers=h,
        json={"domain_id": gas_domain_id, "code": "GAS-001", "title": "Annual gas safety check", "cadence": "annual", "effective_date": "2023-01-01"},
    ).json()
    for building in (riverside_house, willow_court, elm_court):
        client.post(
            "/api/v1/compliance/applicability",
            headers=h,
            json={"requirement_id": gas_requirement["id"], "entity_type": "building", "entity_id": building["id"], "applicable_from": "2023-01-01"},
        )
    # Riverside House: compliant. Willow Court and Elm Court: no inspection
    # recorded at all — MISSING_EVIDENCE, giving Board Assurance real
    # variety instead of every building looking identical.
    client.post(
        "/api/v1/compliance/inspections",
        headers=h,
        json={
            "requirement_id": gas_requirement["id"],
            "entity_type": "building",
            "entity_id": riverside_house["id"],
            "inspector": "Gas Safe Engineer Ltd",
            "inspection_date": (TODAY - timedelta(days=100)).isoformat(),
            "result": "SATISFACTORY",
            "next_due_date": (TODAY + timedelta(days=265)).isoformat(),
        },
    )

    client.post(
        "/api/v1/hazards",
        headers=h,
        json={"property_id": riverside_properties[1]["id"], "hazard_type": "DAMP_AND_MOULD", "reported_date": (TODAY - timedelta(days=14)).isoformat(), "severity": "HIGH"},
    )

    client.post(
        "/api/v1/stock-condition-surveys",
        headers=h,
        json={
            "property_id": riverside_properties[2]["id"],
            "survey_date": "2020-01-10",
            "surveyor": "Northern Surveyors Ltd",
            "condition_ratings": {"roof": "FAIR", "windows": "POOR", "heating": "GOOD"},
            "next_survey_due": (TODAY - timedelta(days=30)).isoformat(),  # already overdue — Data Health finding
        },
    )

    scan = client.post("/api/v1/attention/scan", headers=h)
    print(f"Northstar Housing: attention scan -> {scan.json()}")
    print(f"Northstar Housing: seeded {len(riverside_properties) + len(elm_properties)} properties across 2 developments, 3 buildings")


def seed_commercial_domain_data(client: TestClient, org_id: str) -> None:
    h = {"X-Organisation-Id": org_id}

    if client.get("/api/v1/leases", headers=h).json():
        print("Northstar Commercial already has leases — skipping domain data seed")
        return

    properties = [
        client.post("/api/v1/properties", headers=h, json={"address": f"Unit {n}, 12 High Street", "status": "OPERATIONAL"}).json()
        for n in range(1, 4)
    ]
    tenants = [
        client.post("/api/v1/tenants", headers=h, json={"name": name, "contact_details": {"email": f"{name.split()[0].lower()}@example.com"}}).json()
        for name in ("Acme Retail Ltd", "Bramble Cafe Ltd", "Riverside Fitness Ltd")
    ]

    leases = []
    for prop, tenant, rent in zip(properties, tenants, (250000, 180000, 320000)):
        lease = client.post(
            "/api/v1/leases",
            headers=h,
            json={
                "property_id": prop["id"],
                "tenant_id": tenant["id"],
                "lease_start": "2025-01-01",
                "lease_expiry": "2030-01-01",
                "contractual_rent_pence": rent,
                "rent_frequency": "MONTHLY",
            },
        ).json()
        client.post(f"/api/v1/leases/{lease['id']}/status", headers=h, json={"status": "ACTIVE"})
        leases.append(lease)

    period_start = TODAY.replace(day=1)
    obligations = []
    for lease in leases:
        obligation = client.post(
            "/api/v1/rent-obligations",
            headers=h,
            json={
                "lease_id": lease["id"],
                "obligation_type": "RENT",
                "due_date": period_start.isoformat(),
                "period_start": period_start.isoformat(),
                "period_end": (period_start + timedelta(days=27)).isoformat(),
                "amount_due_pence": lease["contractual_rent_pence"],
            },
        ).json()
        obligations.append(obligation)

    # Lease 1 (Acme): paid in full and reconciled. Lease 2 (Bramble):
    # partial payment, sitting in arrears. Lease 3 (Riverside Fitness):
    # nothing paid at all — real variety for arrears/collection-rate.
    client.post(
        "/api/v1/payments",
        headers=h,
        json={"lease_id": leases[0]["id"], "amount_pence": obligations[0]["amount_due_pence"], "received_date": period_start.isoformat(), "payer_reference": "Acme Retail Ltd"},
    )
    client.post(
        "/api/v1/payments",
        headers=h,
        json={"lease_id": leases[1]["id"], "amount_pence": obligations[1]["amount_due_pence"] // 2, "received_date": period_start.isoformat(), "payer_reference": "Bramble Cafe Ltd"},
    )

    scan = client.post("/api/v1/attention/scan", headers=h)
    print(f"Northstar Commercial: attention scan -> {scan.json()}")
    print(f"Northstar Commercial: seeded {len(properties)} units, {len(leases)} active leases")


def main() -> None:
    db = SessionLocal()
    try:
        housing_org, _ = ensure_org_and_owner(
            db,
            slug="northstar-housing",
            name="Northstar Housing (fictional demo)",
            org_type=OrganisationType.HOUSING_ASSOCIATION,
            goals=["understand_portfolio", "monitor_compliance", "manage_new_developments"],
            owner_email=HOUSING_OWNER_EMAIL,
            owner_name="Demo Owner",
        )
        commercial_org, _ = ensure_org_and_owner(
            db,
            slug="northstar-commercial",
            name="Northstar Commercial (fictional demo)",
            org_type=OrganisationType.COMMERCIAL_LANDLORD,
            goals=["understand_portfolio", "manage_rent_and_arrears"],
            owner_email=COMMERCIAL_OWNER_EMAIL,
            owner_name="Demo Owner",
        )
        # Read ids while the session is still open — SessionLocal's
        # default expire_on_commit means every attribute on these ORM
        # objects needs a live session to refresh from, and db.close()
        # below ends that.
        housing_org_id = str(housing_org.id)
        commercial_org_id = str(commercial_org.id)
    finally:
        db.close()

    with TestClient(app) as client:
        _login(client, HOUSING_OWNER_EMAIL)
        seed_housing_domain_data(client, housing_org_id)

        _login(client, COMMERCIAL_OWNER_EMAIL)
        seed_commercial_domain_data(client, commercial_org_id)

    print("\nDone. Sign in at the web app with either:")
    print(f"  Northstar Housing:    {HOUSING_OWNER_EMAIL} / {DEMO_PASSWORD}")
    print(f"  Northstar Commercial: {COMMERCIAL_OWNER_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
