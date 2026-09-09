import uuid
from datetime import date

from pydantic import BaseModel


class CreateTenantRequest(BaseModel):
    name: str
    contact_details: dict = {}


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    contact_details: dict

    model_config = {"from_attributes": True}


class CreateLeaseRequest(BaseModel):
    property_id: uuid.UUID
    tenant_id: uuid.UUID
    lease_start: date
    lease_expiry: date
    break_date: date | None = None
    rent_review_date: date | None = None
    contractual_rent_pence: int
    rent_frequency: str
    service_charge_amount_pence: int | None = None


class UpdateLeaseStatusRequest(BaseModel):
    status: str


class UpdateOccupancyStatusRequest(BaseModel):
    occupancy_status: str


class LeaseOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    tenant_id: uuid.UUID
    lease_reference: str
    lease_start: date
    lease_expiry: date
    break_date: date | None
    rent_review_date: date | None
    contractual_rent_pence: int
    rent_frequency: str
    service_charge_amount_pence: int | None
    occupancy_status: str
    lease_status: str

    model_config = {"from_attributes": True}
