"""Tenancies — architecture/05-commercial-domain.md §1. Gated by
`commercial.read`/`commercial.write` — permissions RBAC has carried
since Sprint 1 (COMMERCIAL_PROPERTY_MANAGER, LEASE_MANAGER) but nothing
has used until now, the same "give an old permission its first real
use" pattern as Sprint 14's operations.read/write and Sprint 15's
operations.compliance."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.commercial.models import Lease, Tenant
from app.commercial.schemas import (
    CreateLeaseRequest,
    CreateTenantRequest,
    LeaseOut,
    TenantOut,
    UpdateLeaseStatusRequest,
    UpdateOccupancyStatusRequest,
)
from app.commercial.service import (
    InvalidLeaseTransitionError,
    TenancyNotFoundError,
    create_lease,
    create_tenant,
    list_leases,
    list_tenants,
    update_lease_status,
    update_occupancy_status,
)
from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission

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
