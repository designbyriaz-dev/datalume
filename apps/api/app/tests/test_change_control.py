import uuid


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


def _building_and_spec(client, org_id, **spec_overrides):
    building = client.post(
        "/api/v1/buildings", headers={"X-Organisation-Id": org_id}, json={"name": "Block A"}
    ).json()
    payload = {
        "related_entity_type": "building",
        "related_entity_id": building["id"],
        "title": "Roofing specification",
        "description": "Slate roof, Welsh slate grade A",
    }
    payload.update(spec_overrides)
    spec = client.post("/api/v1/specifications", headers={"X-Organisation-Id": org_id}, json=payload).json()
    return building, spec


def test_submit_change_control_snapshots_previous_value(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building, spec = _building_and_spec(client, org_id)

    resp = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={
            "specification_id": spec["id"],
            "proposed_value": {"title": "Roofing specification", "description": "Spanish slate grade B"},
            "reason": "Welsh slate supplier ceased trading",
            "impact_description": "No programme impact, same install method",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["change_reference"] == "CHG-000001"
    assert body["specification_id"] == spec["id"]
    assert body["related_entity_type"] == "building"
    assert body["related_entity_id"] == building["id"]
    assert body["status"] == "PROPOSED"
    assert body["previous_value"]["title"] == "Roofing specification"
    assert body["previous_value"]["description"] == "Slate roof, Welsh slate grade A"
    assert body["proposed_value"]["description"] == "Spanish slate grade B"
    assert body["approved_by"] is None
    assert body["implemented_specification_id"] is None


def test_change_control_against_missing_specification_is_404(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": signup["organisation_id"]},
        json={
            "specification_id": str(uuid.uuid4()),
            "proposed_value": {"title": "x"},
            "reason": "y",
        },
    )
    assert resp.status_code == 404


def test_change_control_against_superseded_specification_is_400(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec = _building_and_spec(client, org_id)
    client.post(
        f"/api/v1/specifications/{spec['id']}/versions",
        headers={"X-Organisation-Id": org_id},
        json={"revision": "B"},
    )

    resp = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    )
    assert resp.status_code == 400


def test_full_change_control_workflow_implements_a_new_specification_revision(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    building, spec = _building_and_spec(client, org_id)

    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={
            "specification_id": spec["id"],
            "proposed_value": {"description": "Spanish slate grade B"},
            "reason": "Welsh slate supplier ceased trading",
        },
    ).json()

    review = client.post(
        f"/api/v1/change-control/{change['id']}/start-review", headers={"X-Organisation-Id": org_id}
    )
    assert review.status_code == 200
    assert review.json()["status"] == "UNDER_REVIEW"

    approve = client.post(
        f"/api/v1/change-control/{change['id']}/approve",
        headers={"X-Organisation-Id": org_id},
        json={"external_approval_reference": "CLIENT-APPROVAL-0042"},
    )
    assert approve.status_code == 200
    approved_body = approve.json()
    assert approved_body["status"] == "APPROVED"
    assert approved_body["approved_by"] == signup["user_id"]
    assert approved_body["approved_date"] is not None
    assert approved_body["external_approval_reference"] == "CLIENT-APPROVAL-0042"

    implement = client.post(
        f"/api/v1/change-control/{change['id']}/implement", headers={"X-Organisation-Id": org_id}
    )
    assert implement.status_code == 200
    implemented_body = implement.json()
    assert implemented_body["status"] == "IMPLEMENTED"
    new_spec_id = implemented_body["implemented_specification_id"]
    assert new_spec_id is not None

    old_spec = client.get(f"/api/v1/specifications/{spec['id']}", headers={"X-Organisation-Id": org_id}).json()
    assert old_spec["status"] == "SUPERSEDED"

    new_spec = client.get(f"/api/v1/specifications/{new_spec_id}", headers={"X-Organisation-Id": org_id}).json()
    assert new_spec["status"] == "ACTIVE"
    assert new_spec["revision"] == "B"
    assert new_spec["description"] == "Spanish slate grade B"
    assert new_spec["title"] == "Roofing specification"  # not in proposed_value, carried forward
    assert new_spec["specification_reference"] == spec["specification_reference"]


def test_cannot_implement_a_change_that_has_not_been_approved(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec = _building_and_spec(client, org_id)
    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    ).json()

    resp = client.post(f"/api/v1/change-control/{change['id']}/implement", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 400


def test_reject_change_control(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec = _building_and_spec(client, org_id)
    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    ).json()

    resp = client.post(f"/api/v1/change-control/{change['id']}/reject", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"

    # Rejected is terminal — approving from here is not a valid transition.
    approve = client.post(
        f"/api/v1/change-control/{change['id']}/approve", headers={"X-Organisation-Id": org_id}, json={}
    )
    assert approve.status_code == 400


def test_cancel_change_control_from_approved(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec = _building_and_spec(client, org_id)
    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    ).json()
    client.post(f"/api/v1/change-control/{change['id']}/approve", headers={"X-Organisation-Id": org_id}, json={})

    resp = client.post(f"/api/v1/change-control/{change['id']}/cancel", headers={"X-Organisation-Id": org_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_list_change_control_filters_by_specification(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec_a = _building_and_spec(client, org_id, title="Spec A")
    _, spec_b = _building_and_spec(client, org_id, title="Spec B")
    change_a = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec_a["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    ).json()
    client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec_b["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    )

    filtered = client.get(
        "/api/v1/change-control", headers={"X-Organisation-Id": org_id}, params={"specification_id": spec_a["id"]}
    ).json()
    assert len(filtered) == 1
    assert filtered[0]["id"] == change_a["id"]


def test_change_control_write_requires_permission(client):
    from app.auth.models import Membership, MembershipStatus, User
    from app.auth.router import _get_or_create_role
    from app.core.security import hash_password
    import app.core.db as db_module

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]
    _, spec = _building_and_spec(client, org_id)

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
                organisation_id=uuid.UUID(org_id),
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
        "/api/v1/change-control",
        headers={"X-Organisation-Id": org_id},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    )
    assert resp.status_code == 403


def test_change_control_from_other_org_is_not_found(client):
    signup_a = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    _, spec = _building_and_spec(client, signup_a["organisation_id"])
    change = client.post(
        "/api/v1/change-control",
        headers={"X-Organisation-Id": signup_a["organisation_id"]},
        json={"specification_id": spec["id"], "proposed_value": {"title": "x"}, "reason": "y"},
    ).json()

    client.post("/api/v1/auth/logout")
    signup_b = client.post(
        "/api/v1/auth/signup", json=_signup_payload(email="other@example.com", organisation_name="Other Org")
    ).json()
    resp = client.get(
        f"/api/v1/change-control/{change['id']}", headers={"X-Organisation-Id": signup_b["organisation_id"]}
    )
    assert resp.status_code == 404
