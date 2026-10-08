import uuid
from datetime import datetime

from pydantic import BaseModel


class PlanOut(BaseModel):
    code: str
    name: str
    price_monthly_pence: int | None
    price_annual_pence: int | None
    property_count_tier_min: int
    property_count_tier_max: int | None
    entitlements: dict

    model_config = {"from_attributes": True}


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    status: str
    current_period_end: datetime | None
    plan: PlanOut
    entitlements: dict


class AuditEventOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    action_code: str
    entity_type: str
    entity_id: str | None
    before: dict | None
    after: dict | None
    ip_address: str | None
    created_at: datetime
