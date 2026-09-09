"""Reporting & export — architecture/06-intelligence-layer.md §4. Every
test processes its report job synchronously via
process_pending_report_jobs (same pattern test_attention.py uses for
run_attention_scan_for_all_organisations) rather than waiting on the
real worker loop's timer."""

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


def _process_pending(client):
    import app.core.db as db_module
    from app.worker.jobs.report_generation import process_pending_report_jobs

    db = db_module.SessionLocal()
    try:
        return process_pending_report_jobs(db)
    finally:
        db.close()


def _request_report(client, org_id, report_type, fmt, **filters):
    resp = client.post(
        "/api/v1/reports",
        headers={"X-Organisation-Id": org_id},
        json={"report_type": report_type, "format": fmt, **filters},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_development_summary_report_generates_pdf(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    development = client.post("/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside"}).json()
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": development["id"]},
    )

    job = _request_report(client, org_id, "DEVELOPMENT_SUMMARY", "PDF")
    assert job["status"] == "PENDING"

    result = _process_pending(client)
    assert result.jobs_processed == 1
    assert result.jobs_failed == 0

    status_body = client.get(f"/api/v1/reports/{job['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert status_body["status"] == "READY"
    assert status_body["file_size_bytes"] > 0

    download = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content[:4] == b"%PDF"


def test_handover_readiness_report_generates_xlsx(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    development = client.post("/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside"}).json()
    client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "Flat 1", "development_id": development["id"]},
    )

    job = _request_report(client, org_id, "HANDOVER_READINESS", "XLSX")
    _process_pending(client)

    download = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert download.content[:2] == b"PK"  # XLSX is a zip container


def test_commercial_portfolio_report_csv_reflects_leases(client):
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
        json={
            "lease_id": lease["id"],
            "obligation_type": "RENT",
            "due_date": "2026-01-01",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "amount_due_pence": 250000,
        },
    )

    job = _request_report(
        client, org_id, "COMMERCIAL_PORTFOLIO", "CSV", period_start="2026-01-01", period_end="2026-01-31"
    )
    _process_pending(client)

    download = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    text = download.content.decode("utf-8")
    assert lease["lease_reference"] in text
    assert "Leases" in text


def test_board_level_report_types_require_reports_board_permission(client):
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

    resp = client.post(
        "/api/v1/reports", headers={"X-Organisation-Id": org_id}, json={"report_type": "BOARD_ASSURANCE", "format": "PDF"}
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/v1/reports",
        headers={"X-Organisation-Id": org_id},
        json={"report_type": "COMPLIANCE_EXECUTIVE_SUMMARY", "format": "PDF"},
    )
    assert resp.status_code == 403

    # Development Summary is a plain reports.read report — MANAGER can request it.
    resp = client.post(
        "/api/v1/reports", headers={"X-Organisation-Id": org_id}, json={"report_type": "DEVELOPMENT_SUMMARY", "format": "PDF"}
    )
    assert resp.status_code == 201


def test_executive_role_can_generate_board_assurance_report(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    db = db_module.SessionLocal()
    try:
        user = User(email="exec@northstar-housing.example", name="Exec", password_hash=hash_password("also-a-fine-password"))
        db.add(user)
        db.flush()
        role = _get_or_create_role(db, "EXECUTIVE")
        db.add(Membership(user_id=user.id, organisation_id=uuid.UUID(org_id), role_id=role.id, status=MembershipStatus.ACTIVE))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "exec@northstar-housing.example", "password": "also-a-fine-password"})

    job = _request_report(client, org_id, "BOARD_ASSURANCE", "PDF")
    _process_pending(client)
    download = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})
    assert download.status_code == 200


def test_download_before_ready_returns_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    job = _request_report(client, org_id, "DEVELOPMENT_SUMMARY", "CSV")

    resp = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 400


def test_report_job_from_other_organisation_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_a = signup_a["organisation_id"]
    job = _request_report(client, org_a, "DEVELOPMENT_SUMMARY", "CSV")

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    org_b = signup_b["organisation_id"]

    resp = client.get(f"/api/v1/reports/{job['id']}", headers={"X-Organisation-Id": org_b})
    assert resp.status_code == 404
    resp = client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_b})
    assert resp.status_code == 404


def test_list_reports_orders_most_recent_first(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    first = _request_report(client, org_id, "DEVELOPMENT_SUMMARY", "CSV")
    second = _request_report(client, org_id, "HANDOVER_READINESS", "CSV")

    jobs = client.get("/api/v1/reports", headers={"X-Organisation-Id": org_id}).json()
    assert [j["id"] for j in jobs] == [second["id"], first["id"]]


def test_reports_require_an_organisation_header(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.get("/api/v1/reports")
    assert resp.status_code == 400


def test_report_request_and_download_are_audited(client):
    """Sprint 24 hardening — architecture/09 §1's threat table:
    "Unauthorised export of tenant data... Report/export endpoints...
    are themselves audit events." Request and download must each leave
    a real, queryable AuditEvent row, not just succeed."""
    import app.core.db as db_module
    from app.platform.audit import AuditEvent

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    job = _request_report(client, org_id, "DEVELOPMENT_SUMMARY", "CSV")
    _process_pending(client)
    client.get(f"/api/v1/reports/{job['id']}/download", headers={"X-Organisation-Id": org_id})

    db = db_module.SessionLocal()
    try:
        events = db.query(AuditEvent).filter(AuditEvent.entity_id == job["id"]).order_by(AuditEvent.created_at).all()
    finally:
        db.close()
    action_codes = [e.action_code for e in events]
    assert "report.requested" in action_codes
    assert "report.downloaded" in action_codes
