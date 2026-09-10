"""BillingProvider adapter boundary — architecture/07-platform-services.md §2.

`StripeBillingProvider` is now a real implementation (previously
deferred behind `NullBillingProvider` since Sprint 2, matching the same
"adapter boundary + Null fallback, real implementation when
credentials exist" pattern as `app/integrations/llm_provider.py`
(Anthropic, Sprint 22). `get_billing_provider()` switches on
`settings.stripe_secret_key` — no route code depends on anything beyond
the `BillingProvider` Protocol, so this swap needed no changes outside
this module plus one new webhook endpoint in `platform/router.py`.

**Honest scope**: there is no Stripe account (test-mode or otherwise)
configured in this environment, so `create_checkout_session` and
`create_billing_portal_session` — both genuine network calls to
Stripe's API — have never run against a real account. What *is*
verified for real, without needing any live credentials: webhook
signature verification and event-dispatch logic. Stripe's own SDK can
generate a validly-signed test payload offline
(`stripe.WebhookSignature.generate_signature_header`), so
`handle_webhook_event`'s full state-machine (subscription created ->
active, payment failed -> past due, subscription deleted -> cancelled)
is exercised by real tests against real HMAC-signed events, the same
way this codebase tested everything else possible without live
credentials (see Sprint 22's `NullLLMProvider` fallback tests).

**Webhook design — why events are keyed by subscription metadata, not
processing order**: Stripe does not guarantee webhook delivery order.
The checkout session is created with
`subscription_data={"metadata": {"organisation_id": ...}}`, so the
`organisation_id` propagates onto the real Stripe Subscription object
itself — every `customer.subscription.*` event can look up the
DataLume `Subscription` row via that metadata directly, without
depending on whether `checkout.session.completed` has already been
processed. `checkout.session.completed` still exists as its own
handler (matching architecture's named event list) purely to capture
`stripe_customer_id`/`stripe_subscription_id` as early as possible;
the subscription-event handlers refresh those same two fields anyway,
so processing order between the two never leaves the row inconsistent.

**`current_period_end` moved in the Stripe API**: as of a 2025 API
version, `current_period_start`/`current_period_end` live on each
Subscription Item, not the Subscription object itself (Stripe's
multiple-prices-per-subscription support) — read from
`subscription["items"]["data"][0]["current_period_end"]`, not
`subscription["current_period_end"]` (which no longer exists and would
KeyError). This app only ever creates one line item per subscription,
so the first item is always the right one.
"""

import uuid
from datetime import datetime, timezone
from typing import Protocol

import stripe
import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.organisations.models import Organisation
from app.platform.billing import Plan, Subscription, SubscriptionStatus

logger = structlog.get_logger("datalume.billing")


class BillingNotConfiguredError(Exception):
    pass


class WebhookVerificationError(Exception):
    """Signature didn't verify, or no webhook secret is configured to
    verify against — always a 400, never treated as a retryable 5xx."""


class BillingProvider(Protocol):
    def create_checkout_session(self, organisation: Organisation, plan: Plan) -> str:
        """Returns a redirect URL for the hosted checkout page."""
        ...

    def create_billing_portal_session(self, organisation: Organisation) -> str:
        """Returns a redirect URL for the billing portal."""
        ...

    def handle_webhook_event(self, payload: bytes, signature: str, db: Session) -> None:
        """The only writer of billing state derived from Stripe
        (architecture 07 §2) — needs `db` to update `subscriptions`
        directly, unlike the other two methods which only ever talk to
        Stripe's API."""
        ...


class NullBillingProvider:
    """Active whenever settings.stripe_secret_key is unset."""

    def create_checkout_session(self, organisation: Organisation, plan: Plan) -> str:
        raise BillingNotConfiguredError(
            "Billing is not configured yet — set STRIPE_SECRET_KEY to enable checkout."
        )

    def create_billing_portal_session(self, organisation: Organisation) -> str:
        raise BillingNotConfiguredError(
            "Billing is not configured yet — set STRIPE_SECRET_KEY to enable the billing portal."
        )

    def handle_webhook_event(self, payload: bytes, signature: str, db: Session) -> None:
        raise BillingNotConfiguredError("Billing is not configured yet — no webhook secret set.")


# Stripe subscription statuses -> DataLume's own smaller status set.
# "incomplete" (first payment still processing) is treated the same as
# a trial — not yet failed, not yet confirmed active — rather than
# inventing a status this codebase's UI doesn't know how to render.
_STRIPE_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "trialing": SubscriptionStatus.TRIALING,
    "incomplete": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELLED,
    "incomplete_expired": SubscriptionStatus.CANCELLED,
    "paused": SubscriptionStatus.CANCELLED,
}


class StripeBillingProvider:
    def __init__(self, secret_key: str, webhook_secret: str | None, web_app_url: str):
        self._client = stripe.StripeClient(secret_key)
        self._webhook_secret = webhook_secret
        self._web_app_url = web_app_url.rstrip("/")

    def create_checkout_session(self, organisation: Organisation, plan: Plan) -> str:
        if plan.price_monthly_pence is None:
            raise BillingNotConfiguredError(
                f"{plan.name} has no self-serve price — this plan is contact-sales only."
            )
        subscription = self._get_subscription_row(organisation.id)
        params: dict = {
            "mode": "subscription",
            "client_reference_id": str(organisation.id),
            "line_items": [
                {
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": plan.price_monthly_pence,
                        "recurring": {"interval": "month"},
                        "product_data": {"name": f"DataLume {plan.name}"},
                    },
                    "quantity": 1,
                }
            ],
            "subscription_data": {"metadata": {"organisation_id": str(organisation.id)}},
            "success_url": f"{self._web_app_url}/organisation/billing?checkout=success",
            "cancel_url": f"{self._web_app_url}/organisation/billing?checkout=cancelled",
        }
        # Reuse the existing Stripe customer if this org has checked out
        # before (e.g. upgrading plan); otherwise let Checkout create one
        # and collect the email itself — omitted entirely rather than
        # passed as an explicit null, since Stripe's API treats a
        # present-but-null field differently from an absent one.
        if subscription and subscription.stripe_customer_id:
            params["customer"] = subscription.stripe_customer_id
        session = self._client.v1.checkout.sessions.create(params)
        return session.url

    def create_billing_portal_session(self, organisation: Organisation) -> str:
        subscription = self._get_subscription_row(organisation.id)
        if subscription is None or not subscription.stripe_customer_id:
            raise BillingNotConfiguredError(
                "No billing customer yet for this organisation — complete checkout first."
            )
        session = self._client.v1.billing_portal.sessions.create(
            {
                "customer": subscription.stripe_customer_id,
                "return_url": f"{self._web_app_url}/organisation/billing",
            }
        )
        return session.url

    def handle_webhook_event(self, payload: bytes, signature: str, db: Session) -> None:
        if not self._webhook_secret:
            raise WebhookVerificationError("No STRIPE_WEBHOOK_SECRET configured to verify against.")
        try:
            event = stripe.Webhook.construct_event(payload, signature, self._webhook_secret)
        except (stripe.error.SignatureVerificationError, ValueError) as exc:
            raise WebhookVerificationError(str(exc)) from exc

        handler = _WEBHOOK_HANDLERS.get(event["type"])
        if handler is None:
            logger.info("billing.webhook.unhandled_event_type", event_type=event["type"])
            return
        handler(event["data"]["object"].to_dict(), db)
        db.commit()

    def _get_subscription_row(self, organisation_id: uuid.UUID) -> Subscription | None:
        # Not exposed via a shared session here — StripeBillingProvider
        # only needs read access to look up a possibly-already-known
        # customer id, via app.core.db directly rather than threading a
        # db session through every Protocol method (only
        # handle_webhook_event writes, so only it takes `db`).
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            return db.query(Subscription).filter(Subscription.organisation_id == organisation_id).first()
        finally:
            db.close()


def _find_subscription_by_organisation_id(db: Session, organisation_id_str: str | None) -> Subscription | None:
    if not organisation_id_str:
        return None
    try:
        organisation_id = uuid.UUID(organisation_id_str)
    except ValueError:
        return None
    return db.query(Subscription).filter(Subscription.organisation_id == organisation_id).first()


def _on_checkout_session_completed(session: dict, db: Session) -> None:
    subscription = _find_subscription_by_organisation_id(db, session.get("client_reference_id"))
    if subscription is None:
        logger.warning("billing.webhook.checkout_completed_unknown_org", client_reference_id=session.get("client_reference_id"))
        return
    subscription.stripe_customer_id = session.get("customer")
    subscription.stripe_subscription_id = session.get("subscription")


def _on_subscription_created_or_updated(stripe_subscription: dict, db: Session) -> None:
    metadata = stripe_subscription.get("metadata") or {}
    subscription = _find_subscription_by_organisation_id(db, metadata.get("organisation_id"))
    if subscription is None:
        logger.warning("billing.webhook.subscription_event_unknown_org", metadata=metadata)
        return

    stripe_status = stripe_subscription.get("status")
    mapped_status = _STRIPE_STATUS_MAP.get(stripe_status)
    if mapped_status is None:
        logger.warning("billing.webhook.unmapped_subscription_status", stripe_status=stripe_status)
    else:
        subscription.status = mapped_status

    subscription.stripe_customer_id = stripe_subscription.get("customer")
    subscription.stripe_subscription_id = stripe_subscription.get("id")

    items = (stripe_subscription.get("items") or {}).get("data") or []
    if items and items[0].get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(items[0]["current_period_end"], tz=timezone.utc)


def _on_subscription_deleted(stripe_subscription: dict, db: Session) -> None:
    metadata = stripe_subscription.get("metadata") or {}
    subscription = _find_subscription_by_organisation_id(db, metadata.get("organisation_id"))
    if subscription is None:
        logger.warning("billing.webhook.subscription_deleted_unknown_org", metadata=metadata)
        return
    subscription.status = SubscriptionStatus.CANCELLED


def _on_invoice_payment_failed(invoice: dict, db: Session) -> None:
    stripe_subscription_id = invoice.get("subscription")
    if not stripe_subscription_id:
        return
    subscription = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_subscription_id).first()
    if subscription is None:
        logger.warning("billing.webhook.invoice_failed_unknown_subscription", stripe_subscription_id=stripe_subscription_id)
        return
    subscription.status = SubscriptionStatus.PAST_DUE


def _on_invoice_payment_succeeded(invoice: dict, db: Session) -> None:
    stripe_subscription_id = invoice.get("subscription")
    if not stripe_subscription_id:
        return
    subscription = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_subscription_id).first()
    if subscription is None:
        return
    # A previously PAST_DUE subscription that pays successfully again
    # goes back to ACTIVE; TRIALING/ACTIVE already-healthy subscriptions
    # are left alone rather than forced ACTIVE early.
    if subscription.status == SubscriptionStatus.PAST_DUE:
        subscription.status = SubscriptionStatus.ACTIVE


_WEBHOOK_HANDLERS = {
    "checkout.session.completed": _on_checkout_session_completed,
    "customer.subscription.created": _on_subscription_created_or_updated,
    "customer.subscription.updated": _on_subscription_created_or_updated,
    "customer.subscription.deleted": _on_subscription_deleted,
    "invoice.payment_failed": _on_invoice_payment_failed,
    "invoice.payment_succeeded": _on_invoice_payment_succeeded,
}


def get_billing_provider() -> BillingProvider:
    settings = get_settings()
    if not settings.stripe_secret_key:
        return NullBillingProvider()
    return StripeBillingProvider(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        web_app_url=settings.web_app_url,
    )
