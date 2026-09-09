"""Defect & Snagging Register — architecture/03-development-domain.md §8,
spec §34-35. Kept separate from warranties_router.py for the same
reason every other *_router.py in this module is separate: a different
URL prefix, not a different module boundary — though defects and
warranties share the same independent multi-attachment shape."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.defects_intelligence import get_defects_intelligence
from app.development.models import Defect
from app.development.schemas import CreateDefectRequest, DefectOut, DefectsIntelligenceOut, UpdateDefectStatusRequest
from app.development.service import (
    HierarchyNotFoundError,
    InvalidDefectTransitionError,
    create_defect,
    update_defect_status,
)

router = APIRouter(tags=["development"])


def _get_org_defect(db: Session, organisation_id: uuid.UUID, defect_id: uuid.UUID) -> Defect:
    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.organisation_id == organisation_id).first()
    if defect is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Defect not found")
    return defect


@router.post("/api/v1/defects", response_model=DefectOut, status_code=status.HTTP_201_CREATED)
def add_defect(
    payload: CreateDefectRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        defect = create_defect(
            db,
            ctx.organisation_id,
            category=payload.category,
            description=payload.description,
            reported_date=payload.reported_date,
            severity=payload.severity,
            contractor=payload.contractor,
            responsible_party=payload.responsible_party,
            target_date=payload.target_date,
            estimated_cost_pence=payload.estimated_cost_pence,
            warranty_related=payload.warranty_related,
            development_id=payload.development_id,
            building_id=payload.building_id,
            property_id=payload.property_id,
            component_id=payload.component_id,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(defect)
    return defect


@router.post("/api/v1/defects/{defect_id}/status", response_model=DefectOut)
def update_defect_status_endpoint(
    defect_id: uuid.UUID,
    payload: UpdateDefectStatusRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    defect = _get_org_defect(db, ctx.organisation_id, defect_id)
    try:
        update_defect_status(
            db,
            ctx.organisation_id,
            defect,
            new_status=payload.status,
            completion_date=payload.completion_date,
            actual_cost_pence=payload.actual_cost_pence,
            actor_user_id=ctx.user.id,
        )
    except InvalidDefectTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(defect)
    return defect


@router.get("/api/v1/defects/intelligence", response_model=DefectsIntelligenceOut)
def defects_intelligence(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return get_defects_intelligence(
        db, ctx.organisation_id, development_id=development_id, building_id=building_id
    )


@router.get("/api/v1/defects", response_model=list[DefectOut])
def list_defects(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    defect_status: str | None = None,
    warranty_related: bool | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Defect).filter(Defect.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(Defect.development_id == development_id)
    if building_id is not None:
        query = query.filter(Defect.building_id == building_id)
    if property_id is not None:
        query = query.filter(Defect.property_id == property_id)
    if component_id is not None:
        query = query.filter(Defect.component_id == component_id)
    if defect_status is not None:
        query = query.filter(Defect.status == defect_status)
    if warranty_related is not None:
        query = query.filter(Defect.warranty_related == warranty_related)
    return query.order_by(Defect.reported_date.desc()).all()


@router.get("/api/v1/defects/{defect_id}", response_model=DefectOut)
def get_defect(
    defect_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return _get_org_defect(db, ctx.organisation_id, defect_id)
