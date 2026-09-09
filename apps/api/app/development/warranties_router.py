"""Warranty Register — architecture/03-development-domain.md §8, spec
§36. Kept separate from defects_router.py for the same reason every
other *_router.py in this module is separate: a different URL prefix."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.models import Warranty
from app.development.presenters import warranties_to_out, warranty_to_out
from app.development.schemas import CreateWarrantyRequest, WarrantyOut
from app.development.service import HierarchyMismatchError, HierarchyNotFoundError, create_warranty, void_warranty

router = APIRouter(tags=["development"])


def _get_org_warranty(db: Session, organisation_id: uuid.UUID, warranty_id: uuid.UUID) -> Warranty:
    warranty = (
        db.query(Warranty).filter(Warranty.id == warranty_id, Warranty.organisation_id == organisation_id).first()
    )
    if warranty is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warranty not found")
    return warranty


@router.post("/api/v1/warranties", response_model=WarrantyOut, status_code=status.HTTP_201_CREATED)
def add_warranty(
    payload: CreateWarrantyRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        warranty = create_warranty(
            db,
            ctx.organisation_id,
            provider=payload.provider,
            warranty_type=payload.warranty_type,
            start_date=payload.start_date,
            expiry_date=payload.expiry_date,
            terms_reference=payload.terms_reference,
            document_id=payload.document_id,
            development_id=payload.development_id,
            building_id=payload.building_id,
            property_id=payload.property_id,
            component_id=payload.component_id,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(warranty)
    return warranty_to_out(warranty)


@router.post("/api/v1/warranties/{warranty_id}/void", response_model=WarrantyOut)
def void_warranty_endpoint(
    warranty_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    warranty = _get_org_warranty(db, ctx.organisation_id, warranty_id)
    void_warranty(db, ctx.organisation_id, warranty, actor_user_id=ctx.user.id)
    db.commit()
    db.refresh(warranty)
    return warranty_to_out(warranty)


@router.get("/api/v1/warranties", response_model=list[WarrantyOut])
def list_warranties(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    expiring_within_days: int | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Warranty).filter(Warranty.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(Warranty.development_id == development_id)
    if building_id is not None:
        query = query.filter(Warranty.building_id == building_id)
    if property_id is not None:
        query = query.filter(Warranty.property_id == property_id)
    if component_id is not None:
        query = query.filter(Warranty.component_id == component_id)
    if expiring_within_days is not None:
        cutoff = date.today() + timedelta(days=expiring_within_days)
        query = query.filter(Warranty.expiry_date <= cutoff, Warranty.expiry_date >= date.today())
    warranties = query.order_by(Warranty.expiry_date).all()
    return warranties_to_out(warranties)


@router.get("/api/v1/warranties/{warranty_id}", response_model=WarrantyOut)
def get_warranty(
    warranty_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    warranty = _get_org_warranty(db, ctx.organisation_id, warranty_id)
    return warranty_to_out(warranty)
