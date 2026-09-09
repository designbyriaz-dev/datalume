def _signup_payload(**overrides):
    payload = {
        "name": "Jamie Ward",
        "email": "jamie@northstar-housing.example",
        "password": "correct-horse-battery",
        "organisation_name": "Northstar Housing",
        "organisation_type": "HOUSING_ASSOCIATION",
        "goals": ["understand_portfolio", "monitor_compliance"],
    }
    payload.update(overrides)
    return payload


def test_signup_creates_org_and_owner_membership(client):
    resp = client.post("/api/v1/auth/signup", json=_signup_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["organisation_slug"] == "northstar-housing"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["email"] == "jamie@northstar-housing.example"
    assert len(me_body["memberships"]) == 1
    assert me_body["memberships"][0]["role_code"] == "OWNER"


def test_signup_rejects_duplicate_email(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.post("/api/v1/auth/signup", json=_signup_payload(organisation_name="Second Org"))
    assert resp.status_code == 409


def test_login_requires_correct_password(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    client.post("/api/v1/auth/logout")

    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "jamie@northstar-housing.example", "password": "wrong-password"},
    )
    assert bad.status_code == 401

    good = client.post(
        "/api/v1/auth/login",
        json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"},
    )
    assert good.status_code == 200


def test_me_requires_authentication(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_workspace_layout_requires_org_header(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.get("/api/v1/workspaces/layout")
    assert resp.status_code == 400


def test_workspace_layout_reflects_organisation_type(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get(
        "/api/v1/workspaces/layout",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 200
    layout = resp.json()
    nav_keys = [s["key"] for s in layout["nav_sections"]]
    assert "developments" in nav_keys
    assert "compliance" in nav_keys
    assert "compliance_rate" in layout["home_kpis"]
