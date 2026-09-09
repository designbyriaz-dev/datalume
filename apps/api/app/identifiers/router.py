from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.identifiers.models import ExternalReference, ReferencePattern
from app.identifiers.schemas import (
    ExternalReferenceOut,
    RecordExternalReferenceRequest,
    ReferencePatternOut,
    UpdateReferencePatternRequest,
)
from app.identifiers.service import list_reference_patterns, record_external_reference, set_reference_pattern

router = APIRouter(prefix="/api/v1", tags=["identifiers"])


@router.post("/external-references", response_model=ExternalReferenceOut, status_code=status.HTTP_201_CREATED)
def add_external_reference(
    payload: RecordExternalReferenceRequest,
    ctx: AuthContext = Depends(require_permission("identifiers.write")),
    db: Session = Depends(get_db),
):
    try:
        ref = record_external_reference(
            db,
            ctx.organisation_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            reference_type=payload.reference_type,
            value=payload.value,
            source_type=SourceType.MANUAL,
            source_system=payload.source,
            actor_user_id=ctx.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(ref)
    return ref


@router.get("/external-references", response_model=list[ExternalReferenceOut])
def list_external_references(
    entity_type: str,
    entity_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return (
        db.query(ExternalReference)
        .filter(
            ExternalReference.organisation_id == ctx.organisation_id,
            ExternalReference.entity_type == entity_type,
            ExternalReference.entity_id == entity_id,
        )
        .all()
    )


@router.get("/reference-patterns", response_model=list[ReferencePatternOut])
def get_reference_patterns(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    patterns = list_reference_patterns(db, ctx.organisation_id)
    db.commit()
    return patterns


@router.patch("/reference-patterns/{entity_type}", response_model=ReferencePatternOut)
def update_reference_pattern(
    entity_type: str,
    payload: UpdateReferencePatternRequest,
    ctx: AuthContext = Depends(require_permission("settings.write")),
    db: Session = Depends(get_db),
):
    if "{sequence" not in payload.pattern:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pattern must include a {sequence} placeholder")
    pattern = set_reference_pattern(db, ctx.organisation_id, entity_type, payload.pattern)
    db.commit()
    db.refresh(pattern)
    return pattern
