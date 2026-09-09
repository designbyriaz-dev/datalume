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


class CreateRentObligationRequest(BaseModel):
    lease_id: uuid.UUID
    obligation_type: str
    due_date: date
    period_start: date
    period_end: date
    amount_due_pence: int
    currency: str = "GBP"
    invoice_reference: str | None = None


class RentObligationOut(BaseModel):
    id: uuid.UUID
    lease_id: uuid.UUID
    obligation_type: str
    due_date: date
    period_start: date
    period_end: date
    amount_due_pence: int
    currency: str
    invoice_reference: str | None
    status: str
    outstanding_pence: int

    model_config = {"from_attributes": True}


class CreatePaymentRequest(BaseModel):
    lease_id: uuid.UUID | None = None
    amount_pence: int
    currency: str = "GBP"
    received_date: date
    payer_reference: str | None = None
    method: str | None = None


class PaymentTransactionOut(BaseModel):
    id: uuid.UUID
    lease_id: uuid.UUID | None
    amount_pence: int
    currency: str
    received_date: date
    payer_reference: str | None
    method: str | None

    model_config = {"from_attributes": True}


class PaymentAllocationOut(BaseModel):
    id: uuid.UUID
    payment_transaction_id: uuid.UUID
    rent_obligation_id: uuid.UUID | None
    amount_allocated_pence: int
    allocation_status: str
    source_type: str

    model_config = {"from_attributes": True}


class CreatePaymentResponse(BaseModel):
    payment: PaymentTransactionOut
    allocation: PaymentAllocationOut


class ResolveAllocationRequest(BaseModel):
    rent_obligation_id: uuid.UUID
    amount_allocated_pence: int


class CreateManualAllocationRequest(BaseModel):
    rent_obligation_id: uuid.UUID
    amount_allocated_pence: int


class PaymentReconciliationConfigOut(BaseModel):
    due_date_window_days: int

    model_config = {"from_attributes": True}


class UpdatePaymentReconciliationConfigRequest(BaseModel):
    due_date_window_days: int


class ArrearsSnapshotOut(BaseModel):
    lease_id: uuid.UUID
    as_of: date
    total_due_pence: int
    outstanding_pence: int
    ageing_pence: dict[str, int]
    credits_pence: int
    unallocated_pence: int


class CollectionRateOut(BaseModel):
    period_start: date
    period_end: date
    due_pence: int
    collected_pence: int
    collection_rate: float
