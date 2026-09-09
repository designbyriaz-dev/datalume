import uuid

import pytest

from app.identifiers.service import get_external_references, record_external_reference
from app.identifiers.models import ExternalReferenceType
from app.core.provenance import SourceType


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


# --- generate_reference / reference patterns --------------------------------


def test_generate_reference_matches_the_pre_sprint_7_format(client):
    """Default patterns render to the exact same strings the old per-module
    COUNT-based generators produced — the upgrade is the concurrency
    guarantee and configurability, not a format change."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    prop1 = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 A St"}
    ).json()
    prop2 = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "2 B St"}
    ).json()
    assert prop1["property_reference"] == "PROP-000001"
    assert prop2["property_reference"] == "PROP-000002"

    dev = client.post(
        "/api/v1/developments", headers={"X-Organisation-Id": org_id}, json={"name": "Riverside Gardens"}
    ).json()
    assert dev["development_reference"] == "DEV-000001"


def test_reference_sequences_are_independent_per_organisation(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    client.post("/api/v1/properties", headers={"X-Organisation-Id": signup_a["organisation_id"]}, json={"address": "1 A St"})

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    prop_b = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": signup_b["organisation_id"]}, json={"address": "1 B St"}
    ).json()
    assert prop_b["property_reference"] == "PROP-000001"  # own counter, unaffected by org A


def test_reference_pattern_is_configurable(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.patch(
        "/api/v1/reference-patterns/PROPERTY",
        headers={"X-Organisation-Id": org_id},
        json={"pattern": "NORTHSTAR-PROP-{sequence:04d}"},
    )
    assert resp.status_code == 200
    assert resp.json()["pattern"] == "NORTHSTAR-PROP-{sequence:04d}"

    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 A St"}
    ).json()
    assert prop["property_reference"] == "NORTHSTAR-PROP-0001"


def test_reference_pattern_update_requires_owner_or_admin(client):
    """OWNER/ADMIN only, via the wildcard permission — settings.write is
    deliberately not granted to any other role."""
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    db = db_module.SessionLocal()
    try:
        manager_user = User(
            email="manager@northstar-housing.example",
            name="Manager Person",
            password_hash=hash_password("also-a-fine-password"),
        )
        db.add(manager_user)
        db.flush()
        manager_role = _get_or_create_role(db, "MANAGER")
        db.add(
            Membership(
                user_id=manager_user.id,
                organisation_id=uuid.UUID(signup["organisation_id"]),
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
        "/api/v1/reference-patterns/PROPERTY",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"pattern": "X-{sequence:04d}"},
    )
    assert resp.status_code == 403


def test_reference_pattern_must_include_sequence_placeholder(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.patch(
        "/api/v1/reference-patterns/PROPERTY",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={"pattern": "NO-PLACEHOLDER-HERE"},
    )
    assert resp.status_code == 400


def test_list_reference_patterns_shows_every_known_type(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get("/api/v1/reference-patterns", headers={"X-Organisation-Id": signup["organisation_id"]})
    assert resp.status_code == 200
    entity_types = {p["entity_type"] for p in resp.json()}
    assert entity_types == {
        "DEVELOPMENT",
        "BUILDING",
        "PROPERTY",
        "DOCUMENT",
        "COMPONENT",
        "SPECIFICATION",
        "CHANGE_CONTROL",
    }


# --- external references -----------------------------------------------------


def test_uprn_recorded_at_property_creation_is_surfaced_on_the_property(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties",
        headers={"X-Organisation-Id": org_id},
        json={"address": "1 A St", "uprn": "100012345678"},
    ).json()
    assert prop["uprn"] == "100012345678"

    fetched = client.get(f"/api/v1/properties/{prop['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert fetched["uprn"] == "100012345678"


def test_planning_and_bsr_references_surfaced_on_development(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    dev = client.post(
        "/api/v1/developments",
        headers={"X-Organisation-Id": org_id},
        json={"name": "Riverside Gardens", "planning_reference": "PL/2026/001", "bsr_reference": "BSR-998877"},
    ).json()
    assert dev["planning_reference"] == "PL/2026/001"
    assert dev["bsr_reference"] == "BSR-998877"
    assert dev["building_control_reference"] is None


def test_add_external_reference_endpoint_and_list(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    prop = client.post(
        "/api/v1/properties", headers={"X-Organisation-Id": org_id}, json={"address": "1 A St"}
    ).json()

    resp = client.post(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": org_id},
        json={
            "entity_type": "property",
            "entity_id": prop["id"],
            "reference_type": "LAND_REGISTRY_REFERENCE",
            "value": "TT123456",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["source_type"] == "MANUAL"

    listed = client.get(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": org_id},
        params={"entity_type": "property", "entity_id": prop["id"]},
    ).json()
    assert len(listed) == 1
    assert listed[0]["reference_type"] == "LAND_REGISTRY_REFERENCE"


def test_external_reference_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
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
    resp = client.post(
        "/api/v1/external-references",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "entity_type": "property",
            "entity_id": "00000000-0000-0000-0000-000000000000",
            "reference_type": "UPRN",
            "value": "999",
        },
    )
    assert resp.status_code == 403


# --- the hard write-path constraint, exercised at the service layer ---------


def test_external_reference_can_never_be_system_generated(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()

    import app.core.db as db_module

    db = db_module.SessionLocal()
    try:
        with pytest.raises(ValueError, match="SYSTEM_GENERATED"):
            record_external_reference(
                db,
                uuid.UUID(signup["organisation_id"]),
                entity_type="property",
                entity_id=uuid.uuid4(),
                reference_type=ExternalReferenceType.UPRN,
                value="999",
                source_type=SourceType.SYSTEM_GENERATED,
            )
    finally:
        db.close()


def test_external_reference_source_type_check_constraint_rejects_system_generated_at_the_db_layer(client):
    """Belt-and-braces: even bypassing the service function entirely and
    inserting the row directly, the DB CHECK constraint refuses it. This
    is the actual 'hard write-path constraint' — not just an application
    convention that a future code path could accidentally skip."""
    import app.core.db as db_module
    from app.identifiers.models import ExternalReference
    from sqlalchemy.exc import IntegrityError

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()

    db = db_module.SessionLocal()
    try:
        bad_ref = ExternalReference(
            organisation_id=uuid.UUID(signup["organisation_id"]),
            entity_type="property",
            entity_id=str(uuid.uuid4()),
            reference_type=ExternalReferenceType.UPRN,
            value="999",
            source_type=SourceType.SYSTEM_GENERATED,
        )
        db.add(bad_ref)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_get_external_references_returns_a_type_to_value_map(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])
    entity_id = uuid.uuid4()

    import app.core.db as db_module

    db = db_module.SessionLocal()
    try:
        record_external_reference(
            db, org_id, entity_type="property", entity_id=entity_id,
            reference_type=ExternalReferenceType.UPRN, value="999", source_type=SourceType.MANUAL,
        )
        record_external_reference(
            db, org_id, entity_type="property", entity_id=entity_id,
            reference_type=ExternalReferenceType.LAND_REGISTRY_REFERENCE, value="TT1", source_type=SourceType.MANUAL,
        )
        db.commit()

        refs = get_external_references(db, org_id, "property", entity_id)
        assert refs == {"UPRN": "999", "LAND_REGISTRY_REFERENCE": "TT1"}
    finally:
        db.close()
