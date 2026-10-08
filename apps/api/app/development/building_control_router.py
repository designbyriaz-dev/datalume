"""Building Control & regulatory mapping — architecture/03-development-domain.md
§5, spec §30. Kept separate from hierarchy_router.py for the same reason
every other *_router.py in this module is separate: a different URL
prefix."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, get_tenant_db, require_permission
from app.development.models import BuildingControlRecord
from app.development.presenters import building_control_record_to_out, building_control_records_to_out
from app.development.schemas import (
    BuildingControlRecordOut,
    CreateBuildingControlRecordRequest,
    UpdateBuildingControlRecordRequest,
)
from app.development.service import HierarchyNotFoundError, create_building_control_record, update_building_control_record

router = APIRouter(tags=["development"])


def _get_org_building_control_record(
    db: Session, organisation_id: uuid.UUID, record_id: uuid.UUID
) -> BuildingControlRecord:
    record = (
        db.query(BuildingControlRecord)
        .filter(BuildingControlRecord.id == record_id, BuildingControlRecord.organisation_id == organisation_id)
        .first()
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Building control record not found")
    return record


@router.post(
    "/api/v1/building-control-records", response_model=BuildingControlRecordOut, status_code=status.HTTP_201_CREATED
)
def add_building_control_record(
    payload: CreateBuildingControlRecordRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_tenant_db),
):
    try:
        record = create_building_control_record(
            db,
            ctx.organisation_id,
            development_id=payload.development_id,
            building_id=payload.building_id,
            body=payload.body,
            application_date=payload.application_date,
            application_reference=payload.application_reference,
            bsr_reference=payload.bsr_reference,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(record)
    return building_control_record_to_out(db, ctx.organisation_id, record)


@router.get("/api/v1/building-control-records", response_model=list[BuildingControlRecordOut])
def list_building_control_records(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_tenant_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(BuildingControlRecord).filter(BuildingControlRecord.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(BuildingControlRecord.development_id == development_id)
    if building_id is not None:
        query = query.filter(BuildingControlRecord.building_id == building_id)
    records = query.order_by(BuildingControlRecord.created_at.desc()).all()
    return building_control_records_to_out(db, ctx.organisation_id, records)


@router.patch("/api/v1/building-control-records/{record_id}", response_model=BuildingControlRecordOut)
def update_building_control_record_endpoint(
    record_id: uuid.UUID,
    payload: UpdateBuildingControlRecordRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_tenant_db),
):
    record = _get_org_building_control_record(db, ctx.organisation_id, record_id)
    try:
        update_building_control_record(
            db,
            ctx.organisation_id,
            record,
            status=payload.status,
            approval_date=payload.approval_date,
            conditions=payload.conditions,
            completion_reference=payload.completion_reference,
            actor_user_id=ctx.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(record)
    return building_control_record_to_out(db, ctx.organisation_id, record)
