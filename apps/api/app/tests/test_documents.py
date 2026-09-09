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


def _upload_document(client, org_id: str, title: str = "Fire door install evidence", content: bytes = b"hello world"):
    return client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={"title": title, "document_type": "EVIDENCE"},
        files={"file": ("evidence.pdf", io.BytesIO(content), "application/pdf")},
    )


def test_upload_document_creates_first_version(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = _upload_document(client, signup["organisation_id"])
    assert resp.status_code == 201
    body = resp.json()
    assert body["revision"] == "A"
    assert body["status"] == "ACTIVE"
    assert body["document_reference"] == "DOC-000001"
    assert body["superseded_by_document_id"] is None
    assert body["size_bytes"] == len(b"hello world")


def test_document_reference_increments_per_organisation(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    first = _upload_document(client, org_id, title="First doc").json()
    second = _upload_document(client, org_id, title="Second doc").json()
    assert first["document_reference"] == "DOC-000001"
    assert second["document_reference"] == "DOC-000002"


def test_new_version_supersedes_previous_without_overwriting(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    v1 = _upload_document(client, org_id, content=b"version one").json()

    v2_resp = client.post(
        f"/api/v1/documents/{v1['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        data={"revision": "B"},
        files={"file": ("evidence-v2.pdf", io.BytesIO(b"version two"), "application/pdf")},
    )
    assert v2_resp.status_code == 201
    v2 = v2_resp.json()
    assert v2["revision"] == "B"
    assert v2["document_reference"] == v1["document_reference"]  # same lineage, same human reference
    assert v2["id"] != v1["id"]  # a NEW row, not an edit of the old one

    detail = client.get(f"/api/v1/documents/{v1['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert len(detail["versions"]) == 2
    v1_after = next(v for v in detail["versions"] if v["id"] == v1["id"])
    assert v1_after["status"] == "SUPERSEDED"
    assert v1_after["superseded_by_document_id"] == v2["id"]

    # The old version's bytes must still be readable — append-only, never overwritten.
    old_download = client.get(f"/api/v1/documents/{v1['id']}/download", headers={"X-Organisation-Id": org_id})
    assert old_download.content == b"version one"
    new_download = client.get(f"/api/v1/documents/{v2['id']}/download", headers={"X-Organisation-Id": org_id})
    assert new_download.content == b"version two"


def test_cannot_version_from_a_superseded_document(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    v1 = _upload_document(client, org_id).json()
    client.post(
        f"/api/v1/documents/{v1['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        data={"revision": "B"},
        files={"file": ("v2.pdf", io.BytesIO(b"v2"), "application/pdf")},
    )
    stale_version_resp = client.post(
        f"/api/v1/documents/{v1['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        data={"revision": "C"},
        files={"file": ("v3.pdf", io.BytesIO(b"v3"), "application/pdf")},
    )
    assert stale_version_resp.status_code == 400


def test_list_documents_defaults_to_current_versions_only(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    v1 = _upload_document(client, org_id).json()
    client.post(
        f"/api/v1/documents/{v1['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        data={"revision": "B"},
        files={"file": ("v2.pdf", io.BytesIO(b"v2"), "application/pdf")},
    )

    current = client.get("/api/v1/documents", headers={"X-Organisation-Id": org_id}).json()
    assert len(current) == 1
    assert current[0]["revision"] == "B"

    all_versions = client.get(
        "/api/v1/documents", headers={"X-Organisation-Id": org_id}, params={"current_only": False}
    ).json()
    assert len(all_versions) == 2


def test_upload_requires_documents_write_permission(client):
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
    resp = _upload_document(client, signup["organisation_id"])
    assert resp.status_code == 403


def test_empty_file_is_rejected(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        data={"title": "Empty", "document_type": "EVIDENCE"},
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert resp.status_code == 400


def test_document_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    doc = _upload_document(client, signup_a["organisation_id"]).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup",
        json=_signup_payload(email="other@example.com", organisation_name="Other Org"),
    ).json()

    resp = client.get(f"/api/v1/documents/{doc['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]})
    assert resp.status_code == 404


def test_dataset_upload_creates_and_links_a_source_document(client):
    """Sprint 4's real integration with Sprint 3: the raw uploaded CSV is
    retained as a Document, not just parsed and discarded."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    csv_bytes = b"Property Address,Type\n12 Elm Street,House\n"

    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": "PROPERTIES", "name": "Linked upload"},
        files={"file": ("properties.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()

    dataset = client.get(f"/api/v1/datasets/{upload['dataset_id']}", headers={"X-Organisation-Id": org_id}).json()
    assert dataset["source_file_document_id"] is not None

    document = client.get(
        f"/api/v1/documents/{dataset['source_file_document_id']}", headers={"X-Organisation-Id": org_id}
    ).json()
    assert document["related_entity_type"] == "dataset"
    assert document["related_entity_id"] == upload["dataset_id"]

    download = client.get(
        f"/api/v1/documents/{dataset['source_file_document_id']}/download",
        headers={"X-Organisation-Id": org_id},
    )
    assert download.content == csv_bytes
