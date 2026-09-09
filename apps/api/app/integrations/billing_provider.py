"""BillingProvider adapter boundary — architecture/07-platform-services.md §2.

Deliberately deferred: this environment has no STRIPE_SECRET_KEY, so
StripeBillingProvider is not implemented yet. NullBillingProvider is what
every route gets today — it fails loudly and specifically ("billing is
not configured") rather than silently no-opping or crashing with an
unrelated error, so the gap is obvious in the API response, not just in
a code comment.

When Stripe credentials exist, implement StripeBillingProvider against
this same Protocol (create_checkout_session, create_billing_portal_session,
handle_webhook_event) using the `stripe` package, and switch it in via
get_billing_provider() below — no other code should need to change,
since app/platform/router.py only ever depends on the Protocol.
"""

from typing import Protocol

from app.core.config import get_settings
from app.organisations.models import Organisation
from app.platform.billing import Plan


class BillingNotConfiguredError(Exception):
    pass


class CheckoutSession(Protocol):
    url: str


class BillingProvider(Protocol):
    def create_checkout_session(self, organisation: Organisation, plan: Plan) -> str:
        """Returns a redirect URL for the hosted checkout page."""
        ...

    def create_billing_portal_session(self, organisation: Organisation) -> str:
        """Returns a redirect URL for the billing portal."""
        ...

    def handle_webhook_event(self, payload: bytes, signature: str) -> None:
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

    def handle_webhook_event(self, payload: bytes, signature: str) -> None:
        raise BillingNotConfiguredError("Billing is not configured yet — no webhook secret set.")


def get_billing_provider() -> BillingProvider:
    settings = get_settings()
    if not settings.stripe_secret_key:
        return NullBillingProvider()
    # StripeBillingProvider(settings.stripe_secret_key) goes here once
    # Stripe credentials are available — see module docstring.
    raise NotImplementedError(
        "STRIPE_SECRET_KEY is set but StripeBillingProvider is not implemented yet."
    )
