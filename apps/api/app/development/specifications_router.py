"""Specification register — architecture/03-development-domain.md §4,
spec §27. Kept separate from router.py/hierarchy_router.py/
components_router.py for the same reason those are separate from each
other: a different URL prefix, not a different module boundary."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.models import Specification, SpecificationStatus
from app.development.schemas import (
    CreateSpecificationRequest,
    ReviseSpecificationRequest,
    SpecificationDetailOut,
    SpecificationOut,
)
from app.development.service import (
    HierarchyMismatchError,
    HierarchyNotFoundError,
    UnsupportedEntityTypeError,
    approve_specification,
    create_specification,
    create_specification_revision,
)

router = APIRouter(tags=["development"])


def _get_org_specification(db: Session, organisation_id: uuid.UUID, specification_id: uuid.UUID) -> Specification:
    spec = (
        db.query(Specification)
        .filter(Specification.id == specification_id, Specification.organisation_id == organisation_id)
        .first()
    )
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Specification not found")
    return spec


@router.post("/api/v1/specifications", response_model=SpecificationOut, status_code=status.HTTP_201_CREATED)
def add_specification(
    payload: CreateSpecificationRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        spec = create_specification(
            db,
            ctx.organisation_id,
            related_entity_type=payload.related_entity_type,
            related_entity_id=payload.related_entity_id,
            title=payload.title,
            description=payload.description,
            related_component_type=payload.related_component_type,
            effective_date=payload.effective_date,
            source_document_id=payload.source_document_id,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except UnsupportedEntityTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(spec)
    return spec


@router.post(
    "/api/v1/specifications/{specification_id}/versions",
    response_model=SpecificationOut,
    status_code=status.HTTP_201_CREATED,
)
def add_specification_revision(
    specification_id: uuid.UUID,
    payload: ReviseSpecificationRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    previous = _get_org_specification(db, ctx.organisation_id, specification_id)
    try:
        new_version = create_specification_revision(
            db,
            ctx.organisation_id,
            previous,
            revision=payload.revision,
            title=payload.title,
            description=payload.description,
            related_component_type=payload.related_component_type,
            effective_date=payload.effective_date,
            source_document_id=payload.source_document_id,
            actor_user_id=ctx.user.id,
        )
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(new_version)
    return new_version


@router.post("/api/v1/specifications/{specification_id}/approve", response_model=SpecificationOut)
def approve_specification_endpoint(
    specification_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    spec = _get_org_specification(db, ctx.organisation_id, specification_id)
    approve_specification(db, ctx.organisation_id, spec, actor_user_id=ctx.user.id)
    db.commit()
    db.refresh(spec)
    return spec


@router.get("/api/v1/specifications", response_model=list[SpecificationOut])
def list_specifications(
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
    current_only: bool = True,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Specification).filter(Specification.organisation_id == ctx.organisation_id)
    if related_entity_type:
        query = query.filter(Specification.related_entity_type == related_entity_type)
    if related_entity_id:
        query = query.filter(Specification.related_entity_id == str(related_entity_id))
    if current_only:
        query = query.filter(Specification.status != SpecificationStatus.SUPERSEDED)
    return query.order_by(Specification.created_at.desc()).all()


@router.get("/api/v1/specifications/{specification_id}", response_model=SpecificationDetailOut)
def get_specification(
    specification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    spec = _get_org_specification(db, ctx.organisation_id, specification_id)
    versions = (
        db.query(Specification)
        .filter(Specification.lineage_id == spec.lineage_id)
        .order_by(Specification.created_at)
        .all()
    )
    return SpecificationDetailOut(**SpecificationOut.model_validate(spec).model_dump(), versions=versions)
