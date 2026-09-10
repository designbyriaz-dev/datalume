import json
import uuid

import pytest
import stripe

import app.core.db as db_module
from app.auth.models import Membership, MembershipStatus, User
from app.auth.router import _get_or_create_role
from app.core.security import hash_password
from app.integrations.billing_provider import (
    BillingNotConfiguredError,
    NullBillingProvider,
    StripeBillingProvider,
    WebhookVerificationError,
)
from app.platform.billing import PLAN_CATALOG, Subscription, SubscriptionStatus, resolve_entitlements

WEBHOOK_SECRET = "whsec_test_only_not_a_real_secret"


def _signed_event(event_type: str, data_object: dict, secret: str = WEBHOOK_SECRET) -> tuple[bytes, str]:
    """Builds a real Stripe event envelope and signs it exactly the way
    Stripe itself does — `stripe.WebhookSignature.generate_signature_header`
    is the SDK's own offline test helper, so this exercises the real
    `stripe.Webhook.construct_event` verification path with no network
    call and no live Stripe account, the same way Sprint 22 tested
    NullLLMProvider's fallback for everything reachable without a real
    Anthropic key."""
    payload = json.dumps(
        {"id": "evt_test", "object": "event", "type": event_type, "data": {"object": data_object}}
    ).encode("utf-8")
    header = stripe.WebhookSignature.generate_signature_header(payload=payload.decode("utf-8"), secret=secret)
    return payload, header


def _provider(webhook_secret: str = WEBHOOK_SECRET) -> StripeBillingProvider:
    return StripeBillingProvider(secret_key="sk_test_fake", webhook_secret=webhook_secret, web_app_url="http://localhost:3100")


def _seed_subscription(db, organisation_id: uuid.UUID, **overrides) -> Subscription:
    from app.platform.billing import get_or_create_plan

    plan = get_or_create_plan(db, "STARTER")
    subscription = db.query(Subscription).filter(Subscription.organisation_id == organisation_id).first()
    if subscription is None:
        subscription = Subscription(organisation_id=organisation_id, plan_id=plan.id, status=SubscriptionStatus.TRIALING)
        db.add(subscription)
    for key, value in overrides.items():
        setattr(subscription, key, value)
    db.commit()
    db.refresh(subscription)
    return subscription


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
        provider.handle_webhook_event(payload=b"{}", signature="sig", db=None)  # type: ignore[arg-type]


def test_resolve_entitlements_handles_missing_subscription():
    assert resolve_entitlements(None) == {}


def test_resolve_entitlements_reads_plan_entitlements():
    class FakePlan:
        entitlements = {"bulk_import": True, "max_users": 5}

    class FakeSubscription:
        plan = FakePlan()

    assert resolve_entitlements(FakeSubscription()) == {"bulk_import": True, "max_users": 5}


# --- StripeBillingProvider.handle_webhook_event ---------------------------
#
# No live Stripe account is configured in this environment (same honest
# scope as anthropic_api_key in Sprint 22), so create_checkout_session and
# create_billing_portal_session — genuine network calls — are untested.
# Everything below is a real network-free test: a real HMAC-signed Stripe
# event envelope, verified through the real stripe.Webhook.construct_event
# path, dispatched through the real handler functions.


def test_checkout_session_completed_sets_customer_and_subscription_ids(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        payload, sig = _signed_event(
            "checkout.session.completed",
            {"client_reference_id": str(org_id), "customer": "cus_e2e", "subscription": "sub_e2e"},
        )
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.stripe_customer_id == "cus_e2e"
        assert subscription.stripe_subscription_id == "sub_e2e"
    finally:
        db.close()


def test_subscription_updated_sets_status_and_period_end_via_metadata(client):
    """No dependency on checkout.session.completed having run first —
    this looks the org up via the subscription's own metadata, the
    ordering-independent design documented in billing_provider.py."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])
    period_end_ts = 1_800_000_000  # 2027-01-15, arbitrary fixed timestamp

    db = db_module.SessionLocal()
    try:
        payload, sig = _signed_event(
            "customer.subscription.updated",
            {
                "id": "sub_e2e",
                "customer": "cus_e2e",
                "status": "active",
                "metadata": {"organisation_id": str(org_id)},
                "items": {"data": [{"current_period_end": period_end_ts}]},
            },
        )
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.stripe_subscription_id == "sub_e2e"
        assert subscription.current_period_end.timestamp() == period_end_ts
    finally:
        db.close()


def test_subscription_deleted_marks_cancelled(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        _seed_subscription(db, org_id, status=SubscriptionStatus.ACTIVE, stripe_customer_id="cus_e2e", stripe_subscription_id="sub_e2e")
        payload, sig = _signed_event(
            "customer.subscription.deleted", {"id": "sub_e2e", "metadata": {"organisation_id": str(org_id)}}
        )
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.status == SubscriptionStatus.CANCELLED
    finally:
        db.close()


def test_invoice_payment_failed_marks_past_due(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        _seed_subscription(db, org_id, status=SubscriptionStatus.ACTIVE, stripe_subscription_id="sub_e2e")
        payload, sig = _signed_event("invoice.payment_failed", {"subscription": "sub_e2e"})
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.status == SubscriptionStatus.PAST_DUE
    finally:
        db.close()


def test_invoice_payment_succeeded_recovers_from_past_due(client):
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        _seed_subscription(db, org_id, status=SubscriptionStatus.PAST_DUE, stripe_subscription_id="sub_e2e")
        payload, sig = _signed_event("invoice.payment_succeeded", {"subscription": "sub_e2e"})
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.status == SubscriptionStatus.ACTIVE
    finally:
        db.close()


def test_invoice_payment_succeeded_does_not_force_trialing_to_active_early(client):
    """A subscription that's still legitimately TRIALING (first invoice
    of a brand new subscription can fire payment_succeeded for a £0
    trial invoice) must not be yanked to ACTIVE before the trial's own
    logic says so."""
    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = uuid.UUID(signup["organisation_id"])

    db = db_module.SessionLocal()
    try:
        _seed_subscription(db, org_id, status=SubscriptionStatus.TRIALING, stripe_subscription_id="sub_e2e")
        payload, sig = _signed_event("invoice.payment_succeeded", {"subscription": "sub_e2e"})
        _provider().handle_webhook_event(payload, sig, db)

        subscription = db.query(Subscription).filter(Subscription.organisation_id == org_id).first()
        assert subscription.status == SubscriptionStatus.TRIALING
    finally:
        db.close()


def test_unknown_event_type_is_a_harmless_no_op(client):
    db = db_module.SessionLocal()
    try:
        payload, sig = _signed_event("customer.updated", {"id": "cus_e2e"})
        _provider().handle_webhook_event(payload, sig, db)  # must not raise
    finally:
        db.close()


def test_webhook_event_for_unknown_organisation_does_not_raise(client):
    """A stale/foreign event (e.g. replayed against the wrong
    environment) must be logged and skipped, never crash the webhook
    endpoint — a 5xx here would make Stripe retry forever."""
    db = db_module.SessionLocal()
    try:
        payload, sig = _signed_event(
            "customer.subscription.updated",
            {"id": "sub_ghost", "customer": "cus_ghost", "status": "active", "metadata": {"organisation_id": str(uuid.uuid4())}},
        )
        _provider().handle_webhook_event(payload, sig, db)  # must not raise
    finally:
        db.close()


def test_bad_signature_is_rejected():
    payload, _ = _signed_event("checkout.session.completed", {"client_reference_id": str(uuid.uuid4())})
    with pytest.raises(WebhookVerificationError):
        _provider().handle_webhook_event(payload, "t=1,v1=not_a_real_signature", db=None)  # type: ignore[arg-type]


def test_missing_webhook_secret_is_rejected():
    payload, sig = _signed_event("checkout.session.completed", {"client_reference_id": str(uuid.uuid4())})
    with pytest.raises(WebhookVerificationError):
        _provider(webhook_secret=None).handle_webhook_event(payload, sig, db=None)  # type: ignore[arg-type]


def test_webhook_endpoint_processes_a_real_signed_event(client, monkeypatch):
    """Proves the actual HTTP route (raw body + Stripe-Signature header,
    no tenant auth) is wired correctly, not just the provider in
    isolation."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)

    signup = client.post("/api/v1/auth/signup", json=_signup_payload()).json()
    org_id = signup["organisation_id"]

    payload, sig = _signed_event(
        "checkout.session.completed",
        {"client_reference_id": org_id, "customer": "cus_http", "subscription": "sub_http"},
    )
    resp = client.post(
        "/api/v1/subscriptions/webhook",
        content=payload,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    db = db_module.SessionLocal()
    try:
        subscription = db.query(Subscription).filter(Subscription.organisation_id == uuid.UUID(org_id)).first()
        assert subscription.stripe_customer_id == "cus_http"
    finally:
        db.close()


def test_webhook_endpoint_rejects_bad_signature(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)

    resp = client.post(
        "/api/v1/subscriptions/webhook",
        content=b'{"type": "checkout.session.completed"}',
        headers={"Stripe-Signature": "t=1,v1=forged", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
