"""CSV import for repairs and compliance inspections — spec §77's
"Upload repairs"/"Upload compliance", the two Housing Operations
Acceptance Test items that genuinely didn't exist on either side of the
stack (Post-Sprint-24 audit) until app/operations/importers.py. Both
reuse _trigger_and_process_import from test_ingestion.py's own module,
matching every other importer's test pattern in this codebase exactly.
"""

from app.tests.test_ingestion import _trigger_and_process_import, _upload_csv


def _signup_payload(**overrides):
    payload = {
        "name": "Jamie Ward",
        "email": "jamie@northstar-housing-ops.example",
        "password": "correct-horse-battery",
        "organisation_name": "Northstar Housing Ops",
        "organisation_type": "HOUSING_ASSOCIATION",
        "goals": [],
    }
    payload.update(overrides)
    return payload


def _setup_property(client, org_id, address="E2E Import Unit"):
    return client.post("/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": address}).json()


def _setup_component(client, org_id):
    types = client.get("/api/v1/component-types", headers={"X-Organisation-Id": org_id}).json()
    boiler_type_id = next(t["id"] for t in types if t["code"] == "BOILERS")
    return client.post(
        "/api/v1/components", headers={"X-Organisation-Id": org_id}, json={"component_type_id": boiler_type_id}
    ).json()


def _setup_requirement(client, org_id, code="GAS-001"):
    domains = client.get("/api/v1/compliance/domains", headers={"X-Organisation-Id": org_id}).json()
    domain_id = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")
    return client.post(
        "/api/v1/compliance/requirements",
        headers={"X-Organisation-Id": org_id},
        json={"domain_id": domain_id, "code": code, "title": "Annual gas safety check", "effective_date": "2024-01-01"},
    ).json()


def test_ingestion_imports_repairs_linked_to_an_existing_property_and_component(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _setup_property(client, org_id)
    component = _setup_component(client, org_id)

    csv_text = (
        "Property Reference,Component Reference,Category,Description,Reported Date,Priority,Contractor\n"
        f"{prop['property_reference']},{component['component_reference']},Heating,Boiler not firing,"
        "2026-02-01,URGENT,Acme Heating Ltd\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="REPAIRS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Property Reference": "property_reference",
                "Component Reference": "component_reference",
                "Category": "category",
                "Description": "description",
                "Reported Date": "reported_date",
                "Priority": "priority",
                "Contractor": "contractor",
            }
        },
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["entities_created"] == 1
    assert body["rows_failed"] == 0

    repairs = client.get(
        "/api/v1/repairs", headers={"X-Organisation-Id": org_id}, params={"property_id": prop["id"]}
    ).json()
    assert len(repairs) == 1
    assert repairs[0]["category"] == "Heating"
    assert repairs[0]["priority"] == "URGENT"
    assert repairs[0]["component_id"] == component["id"]
    assert repairs[0]["contractor"] == "Acme Heating Ltd"


def test_ingestion_repair_with_unmatched_property_reference_fails_that_row_only(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _setup_property(client, org_id)

    csv_text = (
        "Property Reference,Category,Description,Reported Date\n"
        f"{prop['property_reference']},Plumbing,Leaking tap,2026-02-01\n"
        "PROP-999999,Plumbing,Leaking tap,2026-02-01\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="REPAIRS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Property Reference": "property_reference",
                "Category": "category",
                "Description": "description",
                "Reported Date": "reported_date",
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
    assert "PROP-999999" in rows[0]["errors"][0]


def test_ingestion_imports_compliance_inspections_against_a_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _setup_property(client, org_id)
    requirement = _setup_requirement(client, org_id)

    csv_text = (
        "Requirement Code,Entity Type,Entity Reference,Inspector,Inspection Date,Result,Next Due Date\n"
        f"{requirement['code']},property,{prop['property_reference']},A Contractor,2026-02-01,"
        "SATISFACTORY,2027-02-01\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="COMPLIANCE_INSPECTIONS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Requirement Code": "requirement_code",
                "Entity Type": "entity_type",
                "Entity Reference": "entity_reference",
                "Inspector": "inspector",
                "Inspection Date": "inspection_date",
                "Result": "result",
                "Next Due Date": "next_due_date",
            }
        },
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["entities_created"] == 1
    assert body["rows_failed"] == 0

    inspections = client.get(
        "/api/v1/compliance/inspections",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "entity_id": prop["id"], "requirement_id": requirement["id"]},
    ).json()
    assert len(inspections) == 1
    assert inspections[0]["result"] == "SATISFACTORY"
    assert inspections[0]["inspector"] == "A Contractor"
    assert inspections[0]["next_due_date"] == "2027-02-01"


def test_ingestion_compliance_inspection_with_unmatched_requirement_fails_that_row_only(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = _setup_property(client, org_id)

    csv_text = (
        "Requirement Code,Entity Type,Entity Reference,Inspector,Inspection Date,Result\n"
        f"NOT-REAL,property,{prop['property_reference']},A Contractor,2026-02-01,SATISFACTORY\n"
    )
    upload = _upload_csv(client, org_id, csv_text, dataset_type="COMPLIANCE_INSPECTIONS").json()
    client.post(
        f"/api/v1/datasets/{upload['dataset_id']}/mapping",
        headers={"X-Organisation-Id": org_id},
        json={
            "column_mapping": {
                "Requirement Code": "requirement_code",
                "Entity Type": "entity_type",
                "Entity Reference": "entity_reference",
                "Inspector": "inspector",
                "Inspection Date": "inspection_date",
                "Result": "result",
            }
        },
    )

    body = _trigger_and_process_import(client, org_id, upload["dataset_id"])
    assert body["rows_processed"] == 1
    assert body["entities_created"] == 0
    assert body["rows_failed"] == 1

    rows = client.get(
        f"/api/v1/datasets/{upload['dataset_id']}/rows",
        headers={"X-Organisation-Id": org_id},
        params={"row_status": "INVALID"},
    ).json()
    assert len(rows) == 1
    assert "NOT-REAL" in rows[0]["errors"][0]
