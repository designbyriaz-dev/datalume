import pyotp


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


def _signup(client):
    return client.post("/api/v1/auth/signup", json=_signup_payload()).json()


def _enroll_and_enable(client) -> tuple[str, list[str]]:
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    verify = client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    return secret, verify.json()["backup_codes"]


def test_login_unaffected_when_mfa_not_enabled(client):
    _signup(client)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200
    assert resp.json()["mfa_required"] is False
    assert "user_id" in resp.json()


def test_enroll_does_not_enable_mfa_until_verified(client):
    _signup(client)
    enroll = client.post("/api/v1/auth/mfa/enroll")
    assert enroll.status_code == 200
    body = enroll.json()
    assert "secret" in body
    assert body["otpauth_url"].startswith("otpauth://totp/")

    me = client.get("/api/v1/auth/me")
    assert me.json()["mfa_enabled"] is False


def test_verify_wrong_code_rejected(client):
    _signup(client)
    client.post("/api/v1/auth/mfa/enroll")
    resp = client.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
    assert resp.status_code == 400
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is False


def test_verify_enables_mfa_and_login_then_requires_challenge(client):
    _signup(client)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    code = pyotp.TOTP(secret).now()

    verify = client.post("/api/v1/auth/mfa/verify", json={"code": code})
    assert verify.status_code == 200
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is True

    client.post("/api/v1/auth/logout")
    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    assert login.status_code == 200
    body = login.json()
    assert body["mfa_required"] is True
    assert "mfa_token" in body
    assert "user_id" not in body

    # not authenticated yet — the pending mfa_token alone doesn't grant a session
    assert client.get("/api/v1/auth/me").status_code == 401

    challenge = client.post(
        "/api/v1/auth/mfa/challenge", json={"mfa_token": body["mfa_token"], "code": pyotp.TOTP(secret).now()}
    )
    assert challenge.status_code == 200

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "jamie@northstar-housing.example"


def test_challenge_wrong_code_rejected_and_session_not_issued(client):
    _signup(client)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/v1/auth/logout")

    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token = login.json()["mfa_token"]

    bad = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": "111111"})
    assert bad.status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_challenge_rejects_unknown_token(client):
    resp = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": "not-a-real-token", "code": "123456"})
    assert resp.status_code == 401


def test_challenge_token_is_single_use(client):
    _signup(client)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/v1/auth/logout")

    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token = login.json()["mfa_token"]
    code = pyotp.TOTP(secret).now()

    first = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": code})
    assert first.status_code == 200

    replay = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": code})
    assert replay.status_code == 401


def test_disable_requires_correct_password(client):
    _signup(client)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})

    wrong = client.post("/api/v1/auth/mfa/disable", json={"password": "wrong-password"})
    assert wrong.status_code == 401
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is True

    right = client.post("/api/v1/auth/mfa/disable", json={"password": "correct-horse-battery"})
    assert right.status_code == 200
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is False

    client.post("/api/v1/auth/logout")
    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    assert login.json()["mfa_required"] is False


def test_mfa_endpoints_require_authentication(client):
    assert client.post("/api/v1/auth/mfa/enroll").status_code == 401
    assert client.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code == 401
    assert client.post("/api/v1/auth/mfa/disable", json={"password": "x"}).status_code == 401


def test_verify_issues_ten_backup_codes(client):
    _signup(client)
    _secret, codes = _enroll_and_enable(client)
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11 and code[5] == "-"

    me = client.get("/api/v1/auth/me")
    assert me.json()["mfa_backup_codes_remaining"] == 10


def test_backup_code_completes_login_challenge(client):
    _signup(client)
    _secret, codes = _enroll_and_enable(client)
    client.post("/api/v1/auth/logout")

    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token = login.json()["mfa_token"]

    resp = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": codes[0]})
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me").json()["mfa_backup_codes_remaining"] == 9


def test_backup_code_is_single_use(client):
    _signup(client)
    _secret, codes = _enroll_and_enable(client)
    client.post("/api/v1/auth/logout")

    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token1 = login.json()["mfa_token"]
    client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token1, "code": codes[0]})
    client.post("/api/v1/auth/logout")

    login2 = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token2 = login2.json()["mfa_token"]
    replay = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token2, "code": codes[0]})
    assert replay.status_code == 401


def test_backup_code_accepted_without_dash_or_lowercase(client):
    _signup(client)
    _secret, codes = _enroll_and_enable(client)
    client.post("/api/v1/auth/logout")

    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token = login.json()["mfa_token"]
    messy = codes[3].replace("-", "").lower()

    resp = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": messy})
    assert resp.status_code == 200


def test_regenerate_backup_codes_invalidates_old_set(client):
    _signup(client)
    _secret, old_codes = _enroll_and_enable(client)

    wrong = client.post("/api/v1/auth/mfa/backup-codes/regenerate", json={"password": "wrong-password"})
    assert wrong.status_code == 401

    right = client.post("/api/v1/auth/mfa/backup-codes/regenerate", json={"password": "correct-horse-battery"})
    assert right.status_code == 200
    new_codes = right.json()["backup_codes"]
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(set(old_codes))

    client.post("/api/v1/auth/logout")
    login = client.post(
        "/api/v1/auth/login", json={"email": "jamie@northstar-housing.example", "password": "correct-horse-battery"}
    )
    mfa_token = login.json()["mfa_token"]

    old_rejected = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": old_codes[0]})
    assert old_rejected.status_code == 401

    new_accepted = client.post("/api/v1/auth/mfa/challenge", json={"mfa_token": mfa_token, "code": new_codes[0]})
    assert new_accepted.status_code == 200


def test_regenerate_requires_mfa_enabled(client):
    _signup(client)
    resp = client.post("/api/v1/auth/mfa/backup-codes/regenerate", json={"password": "correct-horse-battery"})
    assert resp.status_code == 400


def test_disable_clears_backup_codes(client):
    _signup(client)
    _enroll_and_enable(client)
    client.post("/api/v1/auth/mfa/disable", json={"password": "correct-horse-battery"})

    # re-enroll (a fresh secret) and confirm nothing from the old set survives
    new_secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(new_secret).now()})
    assert client.get("/api/v1/auth/me").json()["mfa_backup_codes_remaining"] == 10
