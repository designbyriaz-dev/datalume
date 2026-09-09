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
