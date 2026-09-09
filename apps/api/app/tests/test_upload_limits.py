"""Sprint 24 hardening — architecture/09-security-testing-ops.md §1's
threat table: "file type/size allow-list" for malicious file upload.
Before app/core/uploads.py, every upload endpoint read an unbounded
request body into memory — a real DoS gap found during this sprint's
threat-model pass, not a hypothetical. These tests use a small,
monkeypatched limit rather than actually allocating 25MB+ per test
run."""

import io

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


@pytest.fixture()
def tiny_upload_limit(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)
    return settings


def test_document_upload_over_the_limit_is_rejected(client, tiny_upload_limit):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    oversized = b"x" * 500
    resp = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={"title": "Huge file", "document_type": "CERTIFICATE"},
        files={"file": ("huge.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert resp.status_code == 413


def test_document_upload_within_the_limit_still_succeeds(client, tiny_upload_limit):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    resp = client.post(
        "/api/v1/documents",
        headers={"X-Organisation-Id": org_id},
        data={"title": "Small file", "document_type": "CERTIFICATE"},
        files={"file": ("small.pdf", io.BytesIO(b"x" * 50), "application/pdf")},
    )
    assert resp.status_code == 201


def test_dataset_upload_over_the_limit_is_rejected(client, tiny_upload_limit):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    oversized_csv = "Property Address,Post Code\n" + "\n".join(f"{i} Elm Street,SW1A {i}AA" for i in range(20))
    resp = client.post(
        "/api/v1/uploads",
        headers={"X-Organisation-Id": org_id},
        data={"dataset_type": "PROPERTIES", "name": "Huge import"},
        files={"file": ("properties.csv", io.BytesIO(oversized_csv.encode()), "text/csv")},
    )
    assert resp.status_code == 413
