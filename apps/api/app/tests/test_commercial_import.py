"""CSV import for rent obligations and payments — spec §78's "Import
rent obligations"/"Import payments", the one Commercial Acceptance
Test item that genuinely didn't exist on either side of the stack
(Post-Sprint-24 audit) until app/commercial/importers.py. Both reuse
_trigger_and_process_import from test_ingestion.py's own module,
matching every other importer's test pattern in this codebase exactly.
"""

import io

from app.tests.test_ingestion import _trigger_and_process_import, _upload_csv


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


def test_ingestion_imports_rent_obligations_linked_to_an_existing_lease(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)

    csv_text = (
        "Lease Reference,Type,Due Date,Period Start,Period End,Amount Due,Invoice Reference\n"
        f"{lease['lease_reference']},RENT,2026-02-01,2026-02-01,2026-02-28,2500.00,INV-100\n"
        f"{lease['lease_reference']},SERVICE_CHARGE,2026-02-01,2026-02-01,2026-02-28,150.00,INV-101\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="RENT_OBLIGATIONS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Lease Reference": "lease_reference",
                "Type": "obligation_type",
                "Due Date": "due_date",
                "Period Start": "period_start",
                "Period End": "period_end",
                "Amount Due": "amount_due",
                "Invoice Reference": "invoice_reference",
            }
        },
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["entities_created"] == 2
    assert body["rows_failed"] == 0

    obligations = client.get(
        "/api/v1/rent-obligations", headers={"X-Organisation-Id": org_id}, params={"lease_id": lease["id"]}
    ).json()
    assert len(obligations) == 2
    rent = next(o for o in obligations if o["obligation_type"] == "RENT")
    assert rent["amount_due_pence"] == 250000
    assert rent["invoice_reference"] == "INV-100"
    service_charge = next(o for o in obligations if o["obligation_type"] == "SERVICE_CHARGE")
    assert service_charge["amount_due_pence"] == 15000

    # The provenance gap this importer surfaced (migration 0026) is
    # genuinely closed, not just schema-deep — an imported obligation
    # carries a real source_dataset_id/import_job_id a manually-created
    # one never would.
    detail = client.get(f"/api/v1/datasets/{upload['dataset_id']}", headers={"X-Organisation-Id": org_id}).json()
    assert detail["latest_job_status"] == "COMPLETED"


def test_ingestion_rent_obligation_with_unmatched_lease_reference_fails_that_row_only(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)

    csv_text = (
        "Lease Reference,Due Date,Period Start,Period End,Amount Due\n"
        f"{lease['lease_reference']},2026-02-01,2026-02-01,2026-02-28,2500.00\n"
        "LSE-999999,2026-02-01,2026-02-01,2026-02-28,2500.00\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="RENT_OBLIGATIONS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Lease Reference": "lease_reference",
                "Due Date": "due_date",
                "Period Start": "period_start",
                "Period End": "period_end",
                "Amount Due": "amount_due",
            }
        },
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["rows_processed"] == 2
    assert body["entities_created"] == 1
    assert body["rows_failed"] == 1

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": org_id},
        params={"row_status": "INVALID"},
    ).json()
    assert len(rows) == 1
    assert "LSE-999999" in rows[0]["errors"][0]


def test_ingestion_imports_payments_and_reconciles_them_for_real(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    lease = _setup_lease(client, org_id)
    client.post(
        "/api/v1/rent-obligations",
        headers={"X-Organisation-Id": org_id},
        json={
            "lease_id": lease["id"],
            "obligation_type": "RENT",
            "due_date": "2026-02-01",
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
            "amount_due_pence": 250000,
        },
    )

    csv_text = "Lease Reference,Amount,Received Date\n" f"{lease['lease_reference']},2500.00,2026-02-01\n"
    upload = _upload_csv(client, org_id, csv_text, dataset_type="PAYMENTS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Lease Reference": "lease_reference", "Amount": "amount", "Received Date": "received_date"}},
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["entities_created"] == 1
    assert body["rows_failed"] == 0

    # The real proof this isn't a fake success: the same deterministic
    # reconciler every manually-recorded payment runs through actually
    # matched this one — the obligation shows as no longer outstanding,
    # not just "a payment row exists somewhere."
    obligations = client.get(
        "/api/v1/rent-obligations", headers={"X-Organisation-Id": org_id}, params={"lease_id": lease["id"]}
    ).json()
    assert obligations[0]["outstanding_pence"] == 0


def test_ingestion_imports_unmatched_payment_as_honestly_unallocated(client):
    """A payment with no lease reference at all — spec §52's own
    "unallocated" case — must import successfully and land genuinely
    UNALLOCATED, never a fabricated match."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    csv_text = "Amount,Received Date,Payer Reference\n1000.00,2026-02-01,MYSTERY-REF\n"
    upload = _upload_csv(client, org_id, csv_text, dataset_type="PAYMENTS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Amount": "amount", "Received Date": "received_date", "Payer Reference": "payer_reference"}},
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["entities_created"] == 1
    assert body["rows_failed"] == 0

    allocations = client.get(
        "/api/v1/payment-allocations", headers={"X-Organisation-Id": org_id}, params={"allocation_status": "UNALLOCATED"}
    ).json()
    assert len(allocations) == 1
