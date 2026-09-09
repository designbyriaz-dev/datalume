"""require_entitlement — architecture/07-platform-services.md §3.

Composed on a route alongside require_permission, same pattern: a route
like a future bulk-XLSX-import endpoint adds
Depends(require_entitlement("bulk_import")) so an org on a plan without
that feature gets a clear "upgrade your plan" response instead of a
generic 403 that looks like an authorisation bug.

No route uses this yet in Sprint 2 — Sprint 3 (Data Ingestion) is the
first real consumer (the upload endpoint). It's tested directly against
resolve_entitlements() in app/tests/test_billing.py in the meantime.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context
from app.platform.billing import Subscription, resolve_entitlements


def require_entitlement(key: str):
    def dependency(
        ctx: AuthContext = Depends(get_auth_context),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        if ctx.organisation_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
        subscription = (
            db.query(Subscription).filter(Subscription.organisation_id == ctx.organisation_id).first()
        )
        entitlements = resolve_entitlements(subscription)
        value = entitlements.get(key)
        if not value:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Your plan does not include '{key}'. Upgrade to unlock this feature.",
            )
        return ctx

    return dependency
