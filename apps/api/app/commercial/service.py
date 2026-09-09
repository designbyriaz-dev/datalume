"""Tenancies — architecture/05-commercial-domain.md §1. Same "manual
entry calls the same function" reasoning as every other *_service.py
in this codebase."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.commercial.models import Lease, LeaseStatus, OccupancyStatus, RentFrequency, Tenant
from app.core.provenance import SourceType
from app.development.models import Property
from app.identifiers.service import generate_reference
from app.platform.audit import record_audit_event


class TenancyNotFoundError(ValueError):
    """A given property_id/tenant_id doesn't exist in this
    organisation — the router maps this to a 404."""


class InvalidLeaseTransitionError(ValueError):
    """The requested status transition isn't allowed from a lease's
    current status — the router maps this to a 400."""


LEASE_TRANSITIONS: dict[LeaseStatus, tuple[LeaseStatus, ...]] = {
    LeaseStatus.DRAFT: (LeaseStatus.ACTIVE, LeaseStatus.TERMINATED),
    LeaseStatus.ACTIVE: (LeaseStatus.EXPIRED, LeaseStatus.TERMINATED, LeaseStatus.RENEWED),
    LeaseStatus.EXPIRED: (),
    LeaseStatus.TERMINATED: (),
    LeaseStatus.RENEWED: (),
}


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = db.query(Property).filter(Property.id == property_id, Property.organisation_id == organisation_id).first()
    if prop is None:
        raise TenancyNotFoundError(f"Property {property_id} not found")
    return prop


def _get_org_tenant(db: Session, organisation_id: uuid.UUID, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.organisation_id == organisation_id).first()
    if tenant is None:
        raise TenancyNotFoundError(f"Tenant {tenant_id} not found")
    return tenant


def create_tenant(
    db: Session, organisation_id: uuid.UUID, *, name: str, contact_details: dict, actor_user_id: uuid.UUID | None
) -> Tenant:
    tenant = Tenant(
        organisation_id=organisation_id,
        name=name,
        contact_details=contact_details,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(tenant)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="tenant.created",
        entity_type="tenant",
        entity_id=str(tenant.id),
        after={"name": name},
    )
    return tenant


def list_tenants(db: Session, organisation_id: uuid.UUID) -> list[Tenant]:
    return db.query(Tenant).filter(Tenant.organisation_id == organisation_id).order_by(Tenant.name).all()


def create_lease(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    property_id: uuid.UUID,
    tenant_id: uuid.UUID,
    lease_start: date,
    lease_expiry: date,
    break_date: date | None,
    rent_review_date: date | None,
    contractual_rent_pence: int,
    rent_frequency: str,
    service_charge_amount_pence: int | None,
    actor_user_id: uuid.UUID | None,
) -> Lease:
    _get_org_property(db, organisation_id, property_id)
    _get_org_tenant(db, organisation_id, tenant_id)

    lease = Lease(
        organisation_id=organisation_id,
        property_id=property_id,
        tenant_id=tenant_id,
        lease_reference=generate_reference(db, organisation_id, "LEASE"),
        lease_start=lease_start,
        lease_expiry=lease_expiry,
        break_date=break_date,
        rent_review_date=rent_review_date,
        contractual_rent_pence=contractual_rent_pence,
        rent_frequency=RentFrequency(rent_frequency),
        service_charge_amount_pence=service_charge_amount_pence,
        occupancy_status=OccupancyStatus.OCCUPIED,
        lease_status=LeaseStatus.DRAFT,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(lease)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="lease.created",
        entity_type="lease",
        entity_id=str(lease.id),
        after={"lease_reference": lease.lease_reference, "property_id": str(property_id), "tenant_id": str(tenant_id)},
    )
    return lease


def list_leases(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    property_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    lease_status: str | None = None,
) -> list[Lease]:
    query = db.query(Lease).filter(Lease.organisation_id == organisation_id)
    if property_id is not None:
        query = query.filter(Lease.property_id == property_id)
    if tenant_id is not None:
        query = query.filter(Lease.tenant_id == tenant_id)
    if lease_status is not None:
        query = query.filter(Lease.lease_status == LeaseStatus(lease_status))
    return query.order_by(Lease.lease_start.desc()).all()


def update_lease_status(
    db: Session, organisation_id: uuid.UUID, lease: Lease, *, new_status: str, actor_user_id: uuid.UUID | None
) -> Lease:
    target = LeaseStatus(new_status)
    allowed = LEASE_TRANSITIONS.get(lease.lease_status, ())
    if target not in allowed:
        raise InvalidLeaseTransitionError(f"Cannot move a lease from {lease.lease_status.value} to {target.value}")

    previous_status = lease.lease_status
    lease.lease_status = target

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="lease.status_changed",
        entity_type="lease",
        entity_id=str(lease.id),
        before={"lease_status": previous_status.value},
        after={"lease_status": target.value},
    )
    return lease


def update_occupancy_status(
    db: Session, organisation_id: uuid.UUID, lease: Lease, *, occupancy_status: str, actor_user_id: uuid.UUID | None
) -> Lease:
    target = OccupancyStatus(occupancy_status)
    previous = lease.occupancy_status
    lease.occupancy_status = target

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="lease.occupancy_changed",
        entity_type="lease",
        entity_id=str(lease.id),
        before={"occupancy_status": previous.value},
        after={"occupancy_status": target.value},
    )
    return lease
