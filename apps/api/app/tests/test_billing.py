import uuid

import pytest

import app.core.db as db_module
from app.auth.models import Membership, MembershipStatus, User
from app.auth.router import _get_or_create_role
from app.core.security import hash_password
from app.integrations.billing_provider import BillingNotConfiguredError, NullBillingProvider
from app.platform.billing import PLAN_CATALOG, resolve_entitlements


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


def test_signup_creates_trialing_starter_subscription(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    resp = client.get(
        "/api/v1/subscriptions",
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "TRIALING"
    assert body["plan"]["code"] == "STARTER"
    assert body["entitlements"]["bulk_import"] is True
    assert body["current_period_end"] is not None


def test_list_plans_returns_full_catalog(client):
    resp = client.get("/api/v1/subscriptions/plans")
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert codes == set(PLAN_CATALOG.keys())


def test_owner_checkout_fails_with_not_configured_not_forbidden(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    # OWNER has billing.manage implicitly via the wildcard role permission
    # set, so this should get past the permission check and fail on the
    # billing provider instead — 503, not 403.
    resp = client.post(
        "/api/v1/subscriptions/checkout",
        params={"plan_code": "PROFESSIONAL"},
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_viewer_cannot_start_checkout(client):
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
        # No membership-invite endpoint exists yet (see STATUS.md) — assign
        # the role directly via the same lazy get-or-create helper signup uses.
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
        "/api/v1/subscriptions/checkout",
        params={"plan_code": "PROFESSIONAL"},
        headers={"X-Organisation-Id": signup["organisation_id"]},
    )
    assert resp.status_code == 403


def test_checkout_without_org_header_is_400(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    resp = client.post("/api/v1/subscriptions/checkout", params={"plan_code": "PROFESSIONAL"})
    assert resp.status_code == 400


def test_null_billing_provider_raises_on_every_action():
    provider = NullBillingProvider()
    with pytest.raises(BillingNotConfiguredError):
        provider.create_checkout_session(organisation=None, plan=None)  # type: ignore[arg-type]
    with pytest.raises(BillingNotConfiguredError):
        provider.create_billing_portal_session(organisation=None)  # type: ignore[arg-type]
    with pytest.raises(BillingNotConfiguredError):
        provider.handle_webhook_event(payload=b"{}", signature="sig")


def test_resolve_entitlements_handles_missing_subscription():
    assert resolve_entitlements(None) == {}


def test_resolve_entitlements_reads_plan_entitlements():
    class FakePlan:
        entitlements = {"bulk_import": True, "max_users": 5}

    class FakeSubscription:
        plan = FakePlan()

    assert resolve_entitlements(FakeSubscription()) == {"bulk_import": True, "max_users": 5}
