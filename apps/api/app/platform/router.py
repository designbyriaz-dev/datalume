from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.integrations.billing_provider import (
    BillingNotConfiguredError,
    BillingProvider,
    WebhookVerificationError,
    get_billing_provider,
)
from app.organisations.models import Organisation
from app.platform.billing import Plan, Subscription, ensure_plan_catalog_seeded, resolve_entitlements
from app.platform.schemas import PlanOut, SubscriptionOut

router = APIRouter(prefix="/api/v1/subscriptions", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    ensure_plan_catalog_seeded(db)
    db.commit()
    return db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.property_count_tier_min).all()


@router.get("", response_model=SubscriptionOut)
def get_subscription(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    subscription = db.query(Subscription).filter(Subscription.organisation_id == ctx.organisation_id).first()
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No subscription found for this organisation")
    return SubscriptionOut(
        id=subscription.id,
        status=subscription.status.value,
        current_period_end=subscription.current_period_end,
        plan=PlanOut.model_validate(subscription.plan),
        entitlements=resolve_entitlements(subscription),
    )


@router.post("/checkout")
def start_checkout(
    plan_code: str,
    ctx: AuthContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
):
    org = db.get(Organisation, ctx.organisation_id)
    ensure_plan_catalog_seeded(db)
    db.commit()
    plan = db.query(Plan).filter(Plan.code == plan_code, Plan.is_active.is_(True)).first()
    if org is None or plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plan")
    try:
        url = provider.create_checkout_session(org, plan)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"checkout_url": url}


@router.post("/portal")
def start_billing_portal(
    ctx: AuthContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
):
    org = db.get(Organisation, ctx.organisation_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    try:
        url = provider.create_billing_portal_session(org)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"portal_url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
):
    """Deliberately no `AuthContext`/tenant scoping — this is called by
    Stripe's own servers, not a logged-in DataLume user. The webhook
    signature (verified inside `handle_webhook_event`) is the entire
    authentication mechanism, per Stripe's own integration model and
    architecture/09 §1's threat table ("Webhook spoofing (Stripe) |
    Signature verification on every webhook before any billing state
    write"). Needs the *raw* request body — signature verification
    hashes the exact bytes Stripe sent, so this can't go through a
    Pydantic-parsed body."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        provider.handle_webhook_event(payload, signature, db)
    except BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except WebhookVerificationError as exc:
        # Not a 5xx: an unsigned/mis-signed request isn't something
        # Stripe should retry, and a 5xx here would make Stripe keep
        # resending a request that will never succeed.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"received": True}
