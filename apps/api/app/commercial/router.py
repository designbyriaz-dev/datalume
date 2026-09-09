"""Tenancies, Rent, Payments & Arrears — architecture/05-commercial-domain.md.
Gated by `commercial.read`/`commercial.write`/`commercial.payments` —
permissions RBAC has carried since Sprint 1 (COMMERCIAL_PROPERTY_MANAGER,
LEASE_MANAGER, RENT_MANAGER) but nothing used until Sprint 19/20, the
same "give an old permission its first real use" pattern as Sprint
14's operations.read/write and Sprint 15's operations.compliance.
`commercial.payments` (narrower than `commercial.write`, RENT_MANAGER-
only) gates the money-recording endpoints specifically — recording a
payment or resolving an ambiguous allocation is a different kind of
action than managing a lease's own terms."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.commercial.arrears import arrears_for_lease as compute_arrears_for_lease
from app.commercial.arrears import collection_rate as compute_collection_rate
from app.commercial.models import AllocationStatus, Lease, PaymentAllocation, PaymentTransaction, RentObligation, Tenant
from app.commercial.reconciliation import match_payment
from app.commercial.schemas import (
    ArrearsSnapshotOut,
    CollectionRateOut,
    CreateLeaseRequest,
    CreateManualAllocationRequest,
    CreatePaymentRequest,
    CreatePaymentResponse,
    CreateRentObligationRequest,
    CreateTenantRequest,
    LeaseOut,
    PaymentAllocationOut,
    PaymentReconciliationConfigOut,
    PaymentTransactionOut,
    RentObligationOut,
    ResolveAllocationRequest,
    TenantOut,
    UpdateLeaseStatusRequest,
    UpdateOccupancyStatusRequest,
    UpdatePaymentReconciliationConfigRequest,
)
from app.commercial.service import (
    InvalidLeaseTransitionError,
    TenancyNotFoundError,
    create_lease,
    create_rent_obligation,
    create_tenant,
    get_or_create_reconciliation_config,
    list_leases,
    list_rent_obligations,
    list_tenants,
    outstanding_for_obligation,
    set_reconciliation_config,
    update_lease_status,
    update_occupancy_status,
)
from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.platform.audit import record_audit_event

router = APIRouter(prefix="/api/v1", tags=["commercial"])


def _get_org_tenant(db: Session, organisation_id: uuid.UUID, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.organisation_id == organisation_id).first()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return tenant


def _get_org_lease(db: Session, organisation_id: uuid.UUID, lease_id: uuid.UUID) -> Lease:
    lease = db.query(Lease).filter(Lease.id == lease_id, Lease.organisation_id == organisation_id).first()
    if lease is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lease not found")
    return lease


def _get_org_obligation(db: Session, organisation_id: uuid.UUID, obligation_id: uuid.UUID) -> RentObligation:
    obligation = (
        db.query(RentObligation)
        .filter(RentObligation.id == obligation_id, RentObligation.organisation_id == organisation_id)
        .first()
    )
    if obligation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rent obligation not found")
    return obligation


def _get_org_payment(db: Session, organisation_id: uuid.UUID, payment_id: uuid.UUID) -> PaymentTransaction:
    payment = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.id == payment_id, PaymentTransaction.organisation_id == organisation_id)
        .first()
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


def _get_org_allocation(db: Session, organisation_id: uuid.UUID, allocation_id: uuid.UUID) -> PaymentAllocation:
    allocation = (
        db.query(PaymentAllocation)
        .filter(PaymentAllocation.id == allocation_id, PaymentAllocation.organisation_id == organisation_id)
        .first()
    )
    if allocation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment allocation not found")
    return allocation


def _obligation_to_out(db: Session, organisation_id: uuid.UUID, obligation: RentObligation) -> RentObligationOut:
    return RentObligationOut(
        id=obligation.id,
        lease_id=obligation.lease_id,
        obligation_type=obligation.obligation_type.value,
        due_date=obligation.due_date,
        period_start=obligation.period_start,
        period_end=obligation.period_end,
        amount_due_pence=obligation.amount_due_pence,
        currency=obligation.currency,
        invoice_reference=obligation.invoice_reference,
        status=obligation.status.value,
        outstanding_pence=outstanding_for_obligation(db, organisation_id, obligation),
    )


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def add_tenant(
    payload: CreateTenantRequest,
    ctx: AuthContext = Depends(require_permission("commercial.write")),
    db: Session = Depends(get_db),
):
    tenant = create_tenant(db, ctx.organisation_id, name=payload.name, contact_details=payload.contact_details, actor_user_id=ctx.user.id)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants", response_model=list[TenantOut])
def get_tenants(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_tenants(db, ctx.organisation_id)


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return _get_org_tenant(db, ctx.organisation_id, tenant_id)


@router.post("/leases", response_model=LeaseOut, status_code=status.HTTP_201_CREATED)
def add_lease(
    payload: CreateLeaseRequest,
    ctx: AuthContext = Depends(require_permission("commercial.write")),
    db: Session = Depends(get_db),
):
    try:
        lease = create_lease(
            db,
            ctx.organisation_id,
            property_id=payload.property_id,
            tenant_id=payload.tenant_id,
            lease_start=payload.lease_start,
            lease_expiry=payload.lease_expiry,
            break_date=payload.break_date,
            rent_review_date=payload.rent_review_date,
            contractual_rent_pence=payload.contractual_rent_pence,
            rent_frequency=payload.rent_frequency,
            service_charge_amount_pence=payload.service_charge_amount_pence,
            actor_user_id=ctx.user.id,
        )
    except TenancyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(lease)
    return lease


@router.get("/leases", response_model=list[LeaseOut])
def get_leases(
    property_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    lease_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_leases(db, ctx.organisation_id, property_id=property_id, tenant_id=tenant_id, lease_status=lease_status)


@router.get("/leases/{lease_id}", response_model=LeaseOut)
def get_lease(
    lease_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return _get_org_lease(db, ctx.organisation_id, lease_id)


@router.post("/leases/{lease_id}/status", response_model=LeaseOut)
def update_lease_status_endpoint(
    lease_id: uuid.UUID,
    payload: UpdateLeaseStatusRequest,
    ctx: AuthContext = Depends(require_permission("commercial.write")),
    db: Session = Depends(get_db),
):
    lease = _get_org_lease(db, ctx.organisation_id, lease_id)
    try:
        update_lease_status(db, ctx.organisation_id, lease, new_status=payload.status, actor_user_id=ctx.user.id)
    except InvalidLeaseTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(lease)
    return lease


@router.post("/leases/{lease_id}/occupancy", response_model=LeaseOut)
def update_occupancy_status_endpoint(
    lease_id: uuid.UUID,
    payload: UpdateOccupancyStatusRequest,
    ctx: AuthContext = Depends(require_permission("commercial.write")),
    db: Session = Depends(get_db),
):
    lease = _get_org_lease(db, ctx.organisation_id, lease_id)
    update_occupancy_status(db, ctx.organisation_id, lease, occupancy_status=payload.occupancy_status, actor_user_id=ctx.user.id)
    db.commit()
    db.refresh(lease)
    return lease


@router.post("/rent-obligations", response_model=RentObligationOut, status_code=status.HTTP_201_CREATED)
def add_rent_obligation(
    payload: CreateRentObligationRequest,
    ctx: AuthContext = Depends(require_permission("commercial.write")),
    db: Session = Depends(get_db),
):
    try:
        obligation = create_rent_obligation(
            db,
            ctx.organisation_id,
            lease_id=payload.lease_id,
            obligation_type=payload.obligation_type,
            due_date=payload.due_date,
            period_start=payload.period_start,
            period_end=payload.period_end,
            amount_due_pence=payload.amount_due_pence,
            currency=payload.currency,
            invoice_reference=payload.invoice_reference,
            actor_user_id=ctx.user.id,
        )
    except TenancyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(obligation)
    return _obligation_to_out(db, ctx.organisation_id, obligation)


@router.get("/rent-obligations", response_model=list[RentObligationOut])
def get_rent_obligations(
    lease_id: uuid.UUID | None = None,
    obligation_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    obligations = list_rent_obligations(db, ctx.organisation_id, lease_id=lease_id, status=obligation_status)
    return [_obligation_to_out(db, ctx.organisation_id, o) for o in obligations]


@router.post("/payments", response_model=CreatePaymentResponse, status_code=status.HTTP_201_CREATED)
def add_payment(
    payload: CreatePaymentRequest,
    ctx: AuthContext = Depends(require_permission("commercial.payments")),
    db: Session = Depends(get_db),
):
    """Records a payment that has already happened elsewhere — never a
    payment initiation (see app/commercial/models.py's own docstring on
    the payment boundary, spec §54). Immediately runs the deterministic
    reconciler against it."""
    if payload.lease_id is not None:
        _get_org_lease(db, ctx.organisation_id, payload.lease_id)

    payment = PaymentTransaction(
        organisation_id=ctx.organisation_id,
        lease_id=payload.lease_id,
        amount_pence=payload.amount_pence,
        currency=payload.currency,
        received_date=payload.received_date,
        payer_reference=payload.payer_reference,
        method=payload.method,
        source_type=SourceType.MANUAL,
        created_by=ctx.user.id,
        updated_by=ctx.user.id,
    )
    db.add(payment)
    db.flush()

    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="payment.recorded",
        entity_type="payment_transaction",
        entity_id=str(payment.id),
        after={"amount_pence": payload.amount_pence, "lease_id": str(payload.lease_id) if payload.lease_id else None},
    )

    allocation = match_payment(db, ctx.organisation_id, payment, actor_user_id=ctx.user.id)
    db.commit()
    db.refresh(payment)
    db.refresh(allocation)
    return CreatePaymentResponse(
        payment=PaymentTransactionOut.model_validate(payment), allocation=PaymentAllocationOut.model_validate(allocation)
    )


@router.get("/payments", response_model=list[PaymentTransactionOut])
def get_payments(
    lease_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(PaymentTransaction).filter(PaymentTransaction.organisation_id == ctx.organisation_id)
    if lease_id is not None:
        query = query.filter(PaymentTransaction.lease_id == lease_id)
    return query.order_by(PaymentTransaction.received_date.desc()).all()


@router.get("/payment-allocations", response_model=list[PaymentAllocationOut])
def get_payment_allocations(
    allocation_status: str | None = None,
    lease_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """The `NEEDS_REVIEW`/`UNALLOCATED`/`POSSIBLE_MATCH` work queue a
    RENT_MANAGER resolves manually — spec §52."""
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(PaymentAllocation).filter(PaymentAllocation.organisation_id == ctx.organisation_id)
    if allocation_status is not None:
        query = query.filter(PaymentAllocation.allocation_status == AllocationStatus(allocation_status))
    if lease_id is not None:
        query = query.join(PaymentTransaction, PaymentTransaction.id == PaymentAllocation.payment_transaction_id).filter(
            PaymentTransaction.lease_id == lease_id
        )
    return query.all()


@router.post("/payment-allocations/{allocation_id}/resolve", response_model=PaymentAllocationOut)
def resolve_payment_allocation(
    allocation_id: uuid.UUID,
    payload: ResolveAllocationRequest,
    ctx: AuthContext = Depends(require_permission("commercial.payments")),
    db: Session = Depends(get_db),
):
    allocation = _get_org_allocation(db, ctx.organisation_id, allocation_id)
    if allocation.allocation_status == AllocationStatus.MATCHED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This allocation is already matched")
    obligation = _get_org_obligation(db, ctx.organisation_id, payload.rent_obligation_id)

    payment = _get_org_payment(db, ctx.organisation_id, allocation.payment_transaction_id)
    already_allocated = (
        db.query(PaymentAllocation)
        .filter(
            PaymentAllocation.organisation_id == ctx.organisation_id,
            PaymentAllocation.payment_transaction_id == payment.id,
            PaymentAllocation.id != allocation.id,
        )
        .with_entities(PaymentAllocation.amount_allocated_pence)
        .all()
    )
    already_allocated_total = sum(row[0] for row in already_allocated)
    if already_allocated_total + payload.amount_allocated_pence > payment.amount_pence:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Allocated amount exceeds the payment received")

    previous_status = allocation.allocation_status
    allocation.rent_obligation_id = obligation.id
    allocation.amount_allocated_pence = payload.amount_allocated_pence
    allocation.allocation_status = AllocationStatus.MATCHED
    allocation.source_type = SourceType.MANUAL

    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="payment_allocation.manually_resolved",
        entity_type="payment_allocation",
        entity_id=str(allocation.id),
        before={"allocation_status": previous_status.value},
        after={"allocation_status": "MATCHED", "rent_obligation_id": str(obligation.id)},
    )
    db.commit()
    db.refresh(allocation)
    return allocation


@router.post("/payments/{payment_id}/allocations", response_model=PaymentAllocationOut, status_code=status.HTTP_201_CREATED)
def add_manual_allocation(
    payment_id: uuid.UUID,
    payload: CreateManualAllocationRequest,
    ctx: AuthContext = Depends(require_permission("commercial.payments")),
    db: Session = Depends(get_db),
):
    """Splitting one payment across several obligations, or applying it
    to instalments, is a deliberate human act — the automatic
    reconciler never does this itself (reconciliation.py's own
    docstring)."""
    payment = _get_org_payment(db, ctx.organisation_id, payment_id)
    obligation = _get_org_obligation(db, ctx.organisation_id, payload.rent_obligation_id)

    already_allocated = (
        db.query(PaymentAllocation)
        .filter(PaymentAllocation.organisation_id == ctx.organisation_id, PaymentAllocation.payment_transaction_id == payment.id)
        .with_entities(PaymentAllocation.amount_allocated_pence)
        .all()
    )
    already_allocated_total = sum(row[0] for row in already_allocated)
    if already_allocated_total + payload.amount_allocated_pence > payment.amount_pence:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Allocated amount exceeds the payment received")

    allocation = PaymentAllocation(
        organisation_id=ctx.organisation_id,
        payment_transaction_id=payment.id,
        rent_obligation_id=obligation.id,
        amount_allocated_pence=payload.amount_allocated_pence,
        allocation_status=AllocationStatus.MATCHED,
        source_type=SourceType.MANUAL,
    )
    db.add(allocation)
    db.flush()

    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="payment_allocation.manually_created",
        entity_type="payment_allocation",
        entity_id=str(allocation.id),
        after={"payment_transaction_id": str(payment.id), "rent_obligation_id": str(obligation.id)},
    )
    db.commit()
    db.refresh(allocation)
    return allocation


@router.get("/payment-reconciliation-config", response_model=PaymentReconciliationConfigOut)
def get_payment_reconciliation_config(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    config = get_or_create_reconciliation_config(db, ctx.organisation_id)
    db.commit()
    db.refresh(config)
    return config


@router.patch("/payment-reconciliation-config", response_model=PaymentReconciliationConfigOut)
def update_payment_reconciliation_config(
    payload: UpdatePaymentReconciliationConfigRequest,
    ctx: AuthContext = Depends(require_permission("commercial.payments")),
    db: Session = Depends(get_db),
):
    config = set_reconciliation_config(db, ctx.organisation_id, due_date_window_days=payload.due_date_window_days)
    db.commit()
    db.refresh(config)
    return config


@router.get("/leases/{lease_id}/arrears", response_model=ArrearsSnapshotOut)
def get_lease_arrears(
    lease_id: uuid.UUID,
    as_of: date | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_lease(db, ctx.organisation_id, lease_id)
    return compute_arrears_for_lease(db, ctx.organisation_id, lease_id, as_of)


@router.get("/collection-rate", response_model=CollectionRateOut)
def get_collection_rate(
    period_start: date,
    period_end: date,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return compute_collection_rate(db, ctx.organisation_id, period_start, period_end)
