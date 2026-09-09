"""Plans, subscriptions, usage — architecture/07-platform-services.md §2.

Money is stored in minor units (pence) as integers, never float, to avoid
rounding drift. Plan/entitlement data is a small fixed catalog defined in
code (PLAN_CATALOG) and lazily upserted into the DB the same way system
roles are (app/auth/router.py._get_or_create_role) — see
get_or_create_plan below.

Stripe itself is deliberately NOT wired up yet (no STRIPE_SECRET_KEY in
this environment) — see app/integrations/billing_provider.py. This
module only builds the DataLume-side model: ORGANISATION -> SUBSCRIPTION
-> PLAN -> ENTITLEMENTS -> USAGE, so nothing here needs to change shape
once real Stripe checkout/webhooks land."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session as OrmSession

from app.core.db import Base


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    price_monthly_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_annual_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    property_count_tier_min: Mapped[int] = mapped_column(Integer)
    property_count_tier_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entitlements: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("organisation_id", name="uq_subscription_organisation"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped[Plan] = relationship()


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    metric: Mapped[str] = mapped_column(String(64))
    value: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# Pricing hypotheses from docs/BUILD_PROMPT.md §64 — "all configurable",
# hence a catalog to edit, not scattered literals.
PLAN_CATALOG: dict[str, dict] = {
    "STARTER": {
        "name": "Starter",
        "price_monthly_pence": 9_900,
        "price_annual_pence": 99_000,
        "property_count_tier_min": 1,
        "property_count_tier_max": 50,
        "entitlements": {"max_properties": 50, "max_users": 5, "bulk_import": True},
    },
    "PROFESSIONAL": {
        "name": "Professional",
        "price_monthly_pence": 29_900,
        "price_annual_pence": 299_000,
        "property_count_tier_min": 51,
        "property_count_tier_max": 500,
        "entitlements": {"max_properties": 500, "max_users": 25, "bulk_import": True},
    },
    "BUSINESS": {
        "name": "Business",
        "price_monthly_pence": 74_900,
        "price_annual_pence": 749_000,
        "property_count_tier_min": 501,
        "property_count_tier_max": 5_000,
        "entitlements": {"max_properties": 5_000, "max_users": 100, "bulk_import": True},
    },
    "ENTERPRISE": {
        "name": "Enterprise",
        "price_monthly_pence": None,
        "price_annual_pence": None,
        "property_count_tier_min": 5_001,
        "property_count_tier_max": None,
        "entitlements": {"max_properties": None, "max_users": None, "bulk_import": True},
    },
}

TRIAL_PLAN_CODE = "STARTER"
TRIAL_LENGTH_DAYS = 14


def get_or_create_plan(db: OrmSession, code: str) -> Plan:
    plan = db.query(Plan).filter(Plan.code == code).first()
    if plan is not None:
        return plan
    if code not in PLAN_CATALOG:
        raise ValueError(f"Unknown plan code: {code}")
    spec = PLAN_CATALOG[code]
    plan = Plan(code=code, **spec)
    db.add(plan)
    db.flush()
    return plan


def ensure_plan_catalog_seeded(db: OrmSession) -> None:
    """Self-healing catalog seed, same lazy-upsert pattern as system roles
    (app/auth/router.py._get_or_create_role). Called from the plans-list
    and checkout endpoints so the full PLAN_CATALOG is always visible —
    relying only on get_or_create_plan(one code) at signup would mean
    PROFESSIONAL/BUSINESS/ENTERPRISE never exist in the DB until someone
    happens to reference them by code."""
    for code in PLAN_CATALOG:
        get_or_create_plan(db, code)
    db.flush()


def resolve_entitlements(subscription: Subscription | None) -> dict:
    """No subscription at all (shouldn't happen post-signup, but defensive)
    resolves to no entitlements rather than raising — callers decide what
    that means for their route."""
    if subscription is None:
        return {}
    return subscription.plan.entitlements
