"""Rent obligations, payments, reconciliation, arrears — architecture/
05-commercial-domain.md §1-3, spec §52's exact/possible/partial/
unallocated matching. Unlike the codebase's purely computed-at-read-
time engines (compliance status, repeat-repair), reconciliation runs
once when a payment is recorded — a config change (e.g. widening the
due-date window) takes effect for payments recorded *after* the
change, not retroactively, matching how a real reconciliation workflow
behaves. Tests that probe config changes create a fresh payment after
the change rather than expecting an old one to be silently reprocessed."""

import uuid
from datetime import date, timedelta


def _signup_payload(**overrides):
    payload = {
        "name": "Jamie Ward",
        "email": "jamie@northstar-commercial.example",
        "password": "correct-horse-battery",
        "organisation_name": "Northstar Commercial",
        "organisation_type": "COMMERCIAL_LANDLORD",
        "goals": [],
    }
    payload.update(overrides)
    return payload


def _setup_lease(client, org_id, address="Unit 1"):
    prop = client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": address}).json()
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
    return lease


def _obligation(client, org_id, lease_id, *, amount_due_pence=250000, due_date="2026-01-01", invoice_reference=None):
    return client.post(
        "/api/v1/rent-obligations",
        headers={"X-Organisation-Id": org_id},
        json={
            "lease_id": lease_id,
            "obligation_type": "RENT",
            "due_date": due_date,
            "period_start": due_date,
            "period_end": due_date,
            "amount_due_pence": amount_due_pence,
            "invoice_reference": invoice_reference,
        },
    ).json()


def _payment(client, org_id, *, lease_id=None, amount_pence, received_date, payer_reference=None):
    resp = client.post(
        "/api/v1/payments",
        headers={"X-Organisation-Id": org_id},
        json={
            "lease_id": lease_id,
            "amount_pence": amount_pence,
            "received_date": received_date,
            "payer_reference": payer_reference,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_rent_obligation(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)

    obligation = _obligation(client, org_id, lease["id"])
    assert obligation["amount_due_pence"] == 250000
    assert obligation["outstanding_pence"] == 250000
    assert obligation["status"] == "ACTIVE"


def test_rule1_exact_reference_match(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    obligation = _obligation(client, org_id, lease["id"], invoice_reference="INV-001")

    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-06-01", payer_reference="INV-001")
    assert result["allocation"]["allocation_status"] == "MATCHED"
    assert result["allocation"]["rent_obligation_id"] == obligation["id"]
    assert result["allocation"]["amount_allocated_pence"] == 250000


def test_rule1_ambiguous_reference_needs_review(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    _obligation(client, org_id, lease["id"], due_date="2026-01-01", invoice_reference="INV-DUP")
    _obligation(client, org_id, lease["id"], due_date="2026-02-01", invoice_reference="INV-DUP")

    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-01-01", payer_reference="INV-DUP")
    assert result["allocation"]["allocation_status"] == "NEEDS_REVIEW"
    assert result["allocation"]["rent_obligation_id"] is None


def test_rule2_exact_amount_lease_and_due_date_window(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    obligation = _obligation(client, org_id, lease["id"], due_date="2026-01-01")

    # 5 days after due_date, within the default 14-day window, no reference.
    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-01-06")
    assert result["allocation"]["allocation_status"] == "MATCHED"
    assert result["allocation"]["rent_obligation_id"] == obligation["id"]


def test_rule2_outside_window_falls_through_to_unallocated(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    _obligation(client, org_id, lease["id"], due_date="2026-01-01")

    # 20 days after due_date — outside the default 14-day window, and the
    # exact-amount match means it's not a "partial" candidate either.
    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-01-21")
    assert result["allocation"]["allocation_status"] == "UNALLOCATED"


def test_widening_due_date_window_lets_a_later_payment_match(client):
    """Config change applies to payments recorded after the change —
    see this module's own docstring."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    _obligation(client, org_id, lease["id"], due_date="2026-01-01")

    resp = client.patch(
        "/api/v1/payment-reconciliation-config", headers={"X-Organisation-Id": org_id}, json={"due_date_window_days": 30}
    )
    assert resp.status_code == 200
    assert resp.json()["due_date_window_days"] == 30

    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-01-21")
    assert result["allocation"]["allocation_status"] == "MATCHED"


def test_rule3_partial_amount_candidate_is_possible_match(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    obligation = _obligation(client, org_id, lease["id"], amount_due_pence=250000, due_date="2026-01-01")

    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=100000, received_date="2026-01-05")
    assert result["allocation"]["allocation_status"] == "POSSIBLE_MATCH"
    assert result["allocation"]["rent_obligation_id"] == obligation["id"]
    assert result["allocation"]["amount_allocated_pence"] == 100000


def test_rule4_no_lease_is_unallocated(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    result = _payment(client, org_id, amount_pence=250000, received_date="2026-01-05")
    assert result["allocation"]["allocation_status"] == "UNALLOCATED"
    assert result["allocation"]["rent_obligation_id"] is None


def test_manual_resolution_of_unallocated_payment(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    obligation = _obligation(client, org_id, lease["id"])

    result = _payment(client, org_id, amount_pence=250000, received_date="2026-01-05")
    allocation_id = result["allocation"]["id"]

    resp = client.post(
        f"/api/v1/payment-allocations/{allocation_id}/resolve",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": obligation["id"], "amount_allocated_pence": 250000},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocation_status"] == "MATCHED"
    assert body["source_type"] == "MANUAL"
    assert body["rent_obligation_id"] == obligation["id"]

    # Already matched — cannot resolve again.
    resp2 = client.post(
        f"/api/v1/payment-allocations/{allocation_id}/resolve",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": obligation["id"], "amount_allocated_pence": 250000},
    )
    assert resp2.status_code == 400


def test_manual_split_allocation_and_overallocation_guard(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    obligation_a = _obligation(client, org_id, lease["id"], amount_due_pence=100000, due_date="2026-01-01")
    obligation_b = _obligation(client, org_id, lease["id"], amount_due_pence=150000, due_date="2026-02-01")

    # A payment covering both obligations combined — no single rule matches
    # a 250000 payment to either 100000 or 150000 obligation individually.
    result = _payment(client, org_id, lease_id=lease["id"], amount_pence=250000, received_date="2026-01-15")
    payment_id = result["payment"]["id"]
    initial_allocation_id = result["allocation"]["id"]

    client.post(
        f"/api/v1/payment-allocations/{initial_allocation_id}/resolve",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": obligation_a["id"], "amount_allocated_pence": 100000},
    )

    resp = client.post(
        f"/api/v1/payments/{payment_id}/allocations",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": obligation_b["id"], "amount_allocated_pence": 150000},
    )
    assert resp.status_code == 201
    assert resp.json()["amount_allocated_pence"] == 150000

    # Now fully allocated — any further split exceeds what was received.
    resp2 = client.post(
        f"/api/v1/payments/{payment_id}/allocations",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": obligation_a["id"], "amount_allocated_pence": 1},
    )
    assert resp2.status_code == 400


def test_arrears_for_lease(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)

    as_of = date(2026, 3, 1)
    overdue_40 = _obligation(client, org_id, lease["id"], amount_due_pence=100000, due_date=(as_of - timedelta(days=40)).isoformat())
    overdue_5 = _obligation(client, org_id, lease["id"], amount_due_pence=50000, due_date=(as_of - timedelta(days=5)).isoformat())
    overpaid = _obligation(client, org_id, lease["id"], amount_due_pence=20000, due_date=(as_of - timedelta(days=10)).isoformat())

    # A payment with no lease_id has no reconciliation candidates at all
    # (rule 4, guaranteed UNALLOCATED) — resolve it manually as a
    # (deliberate) overpayment against the third obligation.
    overpay_result = _payment(client, org_id, amount_pence=25000, received_date=as_of.isoformat())
    assert overpay_result["allocation"]["allocation_status"] == "UNALLOCATED"
    client.post(
        f"/api/v1/payment-allocations/{overpay_result['allocation']['id']}/resolve",
        headers={"X-Organisation-Id": org_id},
        json={"rent_obligation_id": overpaid["id"], "amount_allocated_pence": 25000},
    )

    # An unrelated stray payment, larger than any obligation's own
    # outstanding balance so it can't be picked up as a partial-amount
    # candidate (rule 3) either — genuinely unmatched by any rule.
    stray = _payment(client, org_id, lease_id=lease["id"], amount_pence=999999, received_date=as_of.isoformat())
    assert stray["allocation"]["allocation_status"] == "UNALLOCATED"

    resp = client.get(f"/api/v1/leases/{lease['id']}/arrears", headers={"X-Organisation-Id": org_id}, params={"as_of": as_of.isoformat()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_due_pence"] == 100000 + 50000 + 20000
    assert body["outstanding_pence"] == 100000 + 50000  # overpaid one is fully settled (and then some)
    assert body["ageing_pence"]["31-60"] == 100000
    assert body["ageing_pence"]["1-30"] == 50000
    assert body["credits_pence"] == 5000  # 25000 paid against a 20000 obligation
    assert body["unallocated_pence"] == 999999


def test_collection_rate(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    _obligation(client, org_id, lease["id"], amount_due_pence=100000, due_date="2026-01-01", invoice_reference="INV-A")
    _obligation(client, org_id, lease["id"], amount_due_pence=100000, due_date="2026-01-15", invoice_reference="INV-B")

    _payment(client, org_id, lease_id=lease["id"], amount_pence=100000, received_date="2026-01-01", payer_reference="INV-A")
    # Second obligation left unpaid.

    resp = client.get(
        "/api/v1/collection-rate",
        headers={"X-Organisation-Id": org_id},
        params={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["due_pence"] == 200000
    assert body["collected_pence"] == 100000
    assert body["collection_rate"] == 0.5


def test_payment_write_requires_commercial_payments_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        lease_manager_user = User(
            email="lease-manager@northstar-commercial.example",
            name="Lease Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(lease_manager_user)
        db.flush()
        # LEASE_MANAGER has commercial.write but not commercial.payments —
        # the narrower, money-specific permission this endpoint requires.
        role = _get_or_create_role(db, "LEASE_MANAGER")
        db.add(
            Membership(
                user_id=lease_manager_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "lease-manager@northstar-commercial.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/payments",
        headers={"X-Organisation-Id": org_id},
        json={"amount_pence": 1000, "received_date": "2026-01-01"},
    )
    assert resp.status_code == 403


def test_rent_manager_can_record_payment(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        rent_manager_user = User(
            email="rent-manager@northstar-commercial.example",
            name="Rent Manager",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(rent_manager_user)
        db.flush()
        role = _get_or_create_role(db, "RENT_MANAGER")
        db.add(
            Membership(
                user_id=rent_manager_user.id,
                organisation_id=uuid.UUID(org_id),
                role_id=role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "rent-manager@northstar-commercial.example", "password": "also-a-fine-password"},
    )
    resp = client.post(
        "/api/v1/payments",
        headers={"X-Organisation-Id": org_id},
        json={"amount_pence": 1000, "received_date": "2026-01-01"},
    )
    assert resp.status_code == 201


def test_rent_obligation_against_missing_lease_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.post(
        "/api/v1/rent-obligations",
        headers={"X-Organisation-Id": org_id},
        json={
            "lease_id": str(uuid.uuid4()),
            "obligation_type": "RENT",
            "due_date": "2026-01-01",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "amount_due_pence": 100000,
        },
    )
    assert resp.status_code == 404


def test_payment_allocation_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    result = _payment(client, org_a, amount_pence=1000, received_date="2026-01-01")
    allocation_id = result["allocation"]["id"]

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.post(
        f"/api/v1/payment-allocations/{allocation_id}/resolve",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
        json={"rent_obligation_id": str(uuid.uuid4()), "amount_allocated_pence": 100},
    )
    assert resp.status_code == 404
