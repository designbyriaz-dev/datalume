import io
import uuid

from app.auth.models import Membership, MembershipStatus, User
from app.auth.router import _get_or_create_role
from app.core.security import hash_password


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


def _upload_csv(client, org_id: str, csv_text: str, dataset_type: str = "PROPERTIES", name: str = "My upload"):
    return client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": dataset_type, "name": name},
        files={"file": ("properties.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )


def _build_xlsx_bytes(rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload_xlsx(client, org_id: str, rows: list[list], dataset_type: str = "PROPERTIES", name: str = "My upload"):
    return client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": dataset_type, "name": name},
        files={
            "file": (
                "properties.xlsx",
                io.BytesIO(_build_xlsx_bytes(rows)),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


GOOD_CSV = (
    "Property Address,Post Code,Type\n"
    "12 Elm Street,SW1A 1AA,House\n"
    '"Flat 4, Oak House",SW1A 1AB,Flat\n'  # comma-in-field must be quoted to be well-formed CSV
)


def test_field_dictionaries_endpoint_lists_known_types(client):
    resp = client.get("/api/v1/datasets/field-dictionaries")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"PROPERTIES", "COMPONENTS", "DEVELOPMENTS", "BUILDINGS"}


def test_upload_stages_rows_and_proposes_mapping(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = _upload_csv(client, signup["organisation_id"], GOOD_CSV)
    assert resp.status_code == 201
    body = resp.json()
    assert body["row_count"] == 2
    assert body["proposed_mapping"]["Property Address"] == "address"
    assert body["proposed_mapping"]["Post Code"] == "postcode"
    assert body["proposed_mapping"]["Type"] == "property_type"
    assert body["suggested_mapping_from_template"] is False

    detail = client.get(
        f"/api/v1/datasets/{body['dataset_id']}",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    ).json()
    assert detail["status"] == "VALIDATED"
    assert detail["latest_job_status"] == "AWAITING_MAPPING"
    assert detail["row_status_counts"] == {"PENDING": 2}


def test_unknown_dataset_type_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = _upload_csv(client, signup["organisation_id"], GOOD_CSV, dataset_type="NOT_A_REAL_TYPE")
    assert resp.status_code == 400


def test_empty_csv_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = _upload_csv(client, signup["organisation_id"], "")
    assert resp.status_code == 400


def test_upload_requires_uploads_write_permission(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()

    import app.core.db as db_module

    db = db_module.SessionLocal()
    try:
        viewer_user = User(
            email="viewer@northstar-housing.example",
            name="Viewer Person",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(viewer_user)
        db.flush()
        viewer_role = _get_or_create_role(db, "VIEWER")
        db.add(
            Membership(
                user_id=viewer_user.id,
                organisation_id=uuid.UUID(signup["organisation_id"]),
                role_id=viewer_role.id,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@northstar-housing.example", "password": "also-a-fine-password"},
    )
    resp = _upload_csv(client, signup["organisation_id"], GOOD_CSV)
    assert resp.status_code == 403


def test_apply_mapping_flags_missing_required_fields(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    csv_text = "Property Address,Type\n123 Real Street,House\n,Flat\n"  # second row missing address
    upload = _upload_csv(client, signup["organisation_id"], csv_text).json()

    mapping_resp = client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"column_mapping": {"Property Address": "address", "Type": "property_type"}},
    )
    assert mapping_resp.status_code == 200
    assert mapping_resp.json()["row_status_counts"] == {"VALID": 1, "INVALID": 1}

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        params={"row_status": "INVALID"},
    ).json()
    assert len(rows) == 1
    assert "Missing required field: address" in rows[0]["errors"]


def test_mapping_is_saved_as_reusable_template(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    first = _upload_csv(client, org_id, GOOD_CSV, name="First upload").json()
    client.post(
        f"/api/v1/datasets/{first['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Property Address": "address", "Post Code": "postcode", "Type": "property_type"}},
    )

    # A second upload with the SAME headers should now be auto-mapped from
    # the saved template, without re-running header fuzzy-matching.
    second = _upload_csv(client, org_id, GOOD_CSV, name="Second upload").json()
    assert second["suggested_mapping_from_template"] is True
    assert second["proposed_mapping"]["Property Address"] == "address"


def test_import_without_mapping_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    upload = _upload_csv(client, signup["organisation_id"], GOOD_CSV).json()
    resp = client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/import",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 400


def test_import_with_no_registered_importer_is_an_honest_noop(client):
    """PROPERTIES (Sprint 5) and COMPONENTS (Sprint 8) both have real
    importers now — rather than depend on some other real dataset_type
    staying unregistered forever (fragile: the whole point of IMPORTERS
    is that more get added every sprint), this exercises import_dataset
    directly against a dataset_type that deliberately isn't in
    FIELD_DICTIONARIES or IMPORTERS at all, constructed straight in the
    DB rather than through the /uploads endpoint (which would reject an
    unknown dataset_type before ever reaching this code path)."""
    import app.core.db as db_module
    from app.ingestion.models import Dataset, DatasetStatus, ImportJob, ImportJobStatus, ImportRow, ImportRowStatus
    from app.ingestion.pipeline import import_dataset

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])
    user_id = uuid.UUID(signup["user_id"])

    db = db_module.SessionLocal()
    try:
        dataset = Dataset(
            organisation_id=org_id,
            name="Unregistered type test",
            dataset_type="SOME_FUTURE_DATASET_TYPE",
            status=DatasetStatus.MAPPED,
            row_count=2,
            uploaded_by=user_id,
        )
        db.add(dataset)
        db.flush()
        import_job = ImportJob(
            organisation_id=org_id,
            dataset_id=dataset.id,
            status=ImportJobStatus.MAPPED,
            column_mapping={"Col": "field"},
        )
        db.add(import_job)
        db.flush()
        for i in (1, 2):
            db.add(
                ImportRow(
                    organisation_id=org_id,
                    import_job_id=import_job.id,
                    row_number=i,
                    raw_data={"Col": f"value {i}"},
                    status=ImportRowStatus.VALID,
                    errors=[],
                )
            )
        db.commit()

        result = import_dataset(db, dataset, import_job)
        db.commit()

        assert result == {"rows_processed": 2, "entities_created": 0, "importer_registered": False}

        rows = db.query(ImportRow).filter(ImportRow.import_job_id == import_job.id).all()
        assert all(r.status == ImportRowStatus.IMPORTED for r in rows)
        assert all(r.mapped_entity_type is None for r in rows)
        db.refresh(dataset)
        assert dataset.status == DatasetStatus.IMPORTED
    finally:
        db.close()


def test_ingestion_imports_real_property_entities(client):
    """Sprint 5 registers IMPORTERS["PROPERTIES"] — this is the first
    dataset_type where import_dataset actually creates canonical entities
    instead of the honest no-op above."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    upload = _upload_csv(client, org_id, GOOD_CSV).json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Property Address": "address", "Post Code": "postcode", "Type": "property_type"}},
    )

    resp = client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/import",
        headers={"X-Organisation-Id": org_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["entities_created"] == 2
    assert body["importer_registered"] is True

    properties = client.get("/api/v1/properties", headers={"X-Organisation-Id": org_id}).json()
    assert len(properties) == 2
    addresses = {p["address"] for p in properties}
    assert addresses == {"12 Elm Street", "Flat 4, Oak House"}
    assert all(p["property_reference"].startswith("PROP-") for p in properties)

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": org_id},
    ).json()
    assert all(r["status"] == "IMPORTED" for r in rows)


DEVELOPMENTS_CSV = (
    "Development Name,Address,Postcode,Planned Properties,Planning Reference\n"
    "Riverside Gardens,1 River Road,SW1A 1AA,84,PL/2026/001\n"
    "Oak Court,2 Oak Lane,SW1A 1AB,12,\n"
)


def test_ingestion_imports_real_development_entities(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    upload = _upload_csv(client, org_id, DEVELOPMENTS_CSV, dataset_type="DEVELOPMENTS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Development Name": "name",
                "Address": "address",
                "Postcode": "postcode",
                "Planned Properties": "number_of_planned_properties",
                "Planning Reference": "planning_reference",
            }
        },
    )

    resp = client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["entities_created"] == 2
    assert body["importer_registered"] is True

    developments = client.get("/api/v1/developments", headers={"X-Organisation-Id": org_id}).json()
    assert len(developments) == 2
    names = {d["name"] for d in developments}
    assert names == {"Riverside Gardens", "Oak Court"}
    assert all(d["development_reference"].startswith("DEV-") for d in developments)
    riverside = next(d for d in developments if d["name"] == "Riverside Gardens")
    assert riverside["number_of_planned_properties"] == 84
    assert riverside["planning_reference"] == "PL/2026/001"


BUILDINGS_CSV_TEMPLATE = (
    "Building Name,Type,Storeys,Development Reference\n"
    "Block A,Residential,6,{dev_ref}\n"
    "Unlinked Block,Residential,3,\n"
)


def test_ingestion_imports_buildings_and_links_to_existing_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()

    csv_text = BUILDINGS_CSV_TEMPLATE.format(dev_ref=dev["development_reference"])
    upload = _upload_csv(client, org_id, csv_text, dataset_type="BUILDINGS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Building Name": "name",
                "Type": "building_type",
                "Storeys": "storeys",
                "Development Reference": "development_reference",
            }
        },
    )

    resp = client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert resp.json()["entities_created"] == 2

    buildings = client.get("/api/v1/buildings", headers={"X-Organisation-Id": org_id}).json()
    assert len(buildings) == 2
    linked = next(b for b in buildings if b["name"] == "Block A")
    unlinked = next(b for b in buildings if b["name"] == "Unlinked Block")
    assert linked["development_id"] == dev["id"]
    assert linked["storeys"] == 6
    assert unlinked["development_id"] is None


def test_ingestion_building_with_unknown_development_reference_is_left_unlinked(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    csv_text = "Building Name,Development Reference\nBlock B,DEV-999999\n"
    upload = _upload_csv(client, org_id, csv_text, dataset_type="BUILDINGS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Building Name": "name", "Development Reference": "development_reference"}},
    )
    client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})

    buildings = client.get("/api/v1/buildings", headers={"X-Organisation-Id": org_id}).json()
    assert buildings[0]["development_id"] is None


def test_cleaning_trims_whitespace_and_is_logged(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    csv_text = "Property Address,Type\n  12 Elm Street  ,House\n"
    upload = _upload_csv(client, signup["organisation_id"], csv_text).json()

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    ).json()
    assert rows[0]["raw_data"]["Property Address"] == "12 Elm Street"
    assert rows[0]["raw_data"]["_cleaning"][0]["before"] == "  12 Elm Street  "


def test_upload_blocked_without_bulk_import_entitlement(client):
    """Every seeded plan currently grants bulk_import=True (see
    PLAN_CATALOG), so this proves require_entitlement actually enforces
    something rather than just being present but inert — the first real
    consumer promised in app/platform/entitlements.py's docstring."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()

    import app.core.db as db_module
    from app.platform.billing import Plan, Subscription

    db = db_module.SessionLocal()
    try:
        no_import_plan = Plan(
            code="NO_BULK_IMPORT_TEST_PLAN",
            name="Test Plan Without Bulk Import",
            property_count_tier_min=1,
            entitlements={"bulk_import": False},
        )
        db.add(no_import_plan)
        db.flush()
        subscription = (
            db.query(Subscription)
            .filter(Subscription.organisation_id == uuid.UUID(signup["organisation_id"]))
            .first()
        )
        subscription.plan_id = no_import_plan.id
        db.commit()
    finally:
        db.close()

    resp = _upload_csv(client, signup["organisation_id"], GOOD_CSV)
    assert resp.status_code == 402


def test_ragged_row_is_flagged_not_silently_misaligned(client):
    """Regression test for a bug found by hand-testing against a real CSV:
    an unescaped comma inside 'Flat 4, Oak House' produced one extra cell,
    which used to be silently truncated — shifting every field one column
    to the left and marking the corrupted row VALID/IMPORTED. It must now
    be flagged INVALID and excluded from import instead."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    csv_text = (
        "Property Address,Post Code,Type\n"
        "12 Elm Street,SW1A 1AA,House\n"
        "Flat 4, Oak House,SW1A 1AB,Flat\n"  # unquoted comma -> 4 cells, 3 headers
    )
    upload = _upload_csv(client, org_id, csv_text).json()
    assert upload["row_count"] == 2

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": org_id},
    ).json()
    ragged = next(r for r in rows if r["row_number"] == 2)
    assert ragged["status"] == "INVALID"
    assert "4 values but 3 columns" in ragged["errors"][0]

    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Property Address": "address", "Post Code": "postcode", "Type": "property_type"}},
    )
    detail = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}",
        headers={"X-Organisation-Id": org_id},
    ).json()
    # The ragged row must stay INVALID through mapping, not flip to VALID.
    assert detail["row_status_counts"] == {"VALID": 1, "INVALID": 1}

    import_resp = client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/import",
        headers={"X-Organisation-Id": org_id},
    ).json()
    assert import_resp["rows_processed"] == 1  # only the well-formed row


def test_dataset_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    upload = _upload_csv(client, signup_a["organisation_id"], GOOD_CSV).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()

    resp = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}",
        headers={"X-Organisation-Id": signup_b["organisation_id"]},
    )
    assert resp.status_code == 404


# --- XLSX ---------------------------------------------------------------


def test_field_dictionaries_endpoint_still_correct_after_xlsx(client):
    """Sanity check that adding XLSX support didn't change what dataset
    types exist — it's a new input format for the same set, not a new
    dataset type of its own."""
    resp = client.get("/api/v1/datasets/field-dictionaries")
    assert set(resp.json().keys()) == {"PROPERTIES", "COMPONENTS", "DEVELOPMENTS", "BUILDINGS"}


def test_ingestion_imports_real_property_entities_from_xlsx(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    rows = [
        ["Property Address", "Post Code", "Type"],
        ["12 Elm Street", "SW1A 1AA", "House"],
        ["Flat 4, Oak House", "SW1A 1AB", "Flat"],
    ]
    upload = _upload_xlsx(client, org_id, rows).json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Property Address": "address", "Post Code": "postcode", "Type": "property_type"}},
    )

    resp = client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_processed"] == 2
    assert body["entities_created"] == 2

    properties = client.get("/api/v1/properties", headers={"X-Organisation-Id": org_id}).json()
    addresses = {p["address"] for p in properties}
    assert addresses == {"12 Elm Street", "Flat 4, Oak House"}


def test_xlsx_typed_cells_convert_to_expected_strings(client):
    """openpyxl hands back real Python int/float values for numeric
    cells, not text — an integer-valued Storeys column must land as
    "6", not "6.0", for BUILDINGS' storeys field (parsed with int())
    to work the same way it does from a CSV upload."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    rows = [
        ["Building Name", "Storeys"],
        ["Block A", 6],  # a real int cell, not a string
    ]
    upload = _upload_xlsx(client, org_id, rows, dataset_type="BUILDINGS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={"column_mapping": {"Building Name": "name", "Storeys": "storeys"}},
    )
    client.post(f"/api/v1/datasets/{upload['dataset_id']}/import", headers={"X-Organisation-Id": org_id})

    buildings = client.get("/api/v1/buildings", headers={"X-Organisation-Id": org_id}).json()
    assert buildings[0]["storeys"] == 6


def test_corrupt_xlsx_upload_is_rejected_not_500(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": "PROPERTIES", "name": "Bad file"},
        files={"file": ("properties.xlsx", io.BytesIO(b"this is not a real xlsx file"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_empty_xlsx_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    resp = _upload_xlsx(client, signup["organisation_id"], rows=[])
    assert resp.status_code == 400


def test_xlsx_blank_rows_are_skipped_like_csv(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    rows = [
        ["Property Address", "Post Code", "Type"],
        ["12 Elm Street", "SW1A 1AA", "House"],
        [None, None, None],  # openpyxl represents a fully blank row as all-None cells
        ["2 Oak Lane", "SW1A 1AB", "Flat"],
    ]
    upload = _upload_xlsx(client, org_id, rows).json()
    assert upload["row_count"] == 2
