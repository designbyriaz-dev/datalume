"""Handover Readiness / Handover Workflow — architecture/03-development-domain.md
§8-9, spec §37-38. Kept separate from hierarchy_router.py for the same
reason every other *_router.py in this module is separate: a different
URL prefix."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.handover import CHECK_LABELS, compute_handover_readiness
from app.development.models import Development, HandoverRecord
from app.development.schemas import (
    AuthoriseHandoverRequest,
    HandoverCheckOut,
    HandoverReadinessOut,
    HandoverReadinessWeightOut,
    HandoverRecordOut,
    UpdateHandoverReadinessWeightRequest,
)
from app.development.service import (
    HANDOVER_READINESS_THRESHOLD_PCT,
    HandoverNotReadyError,
    HierarchyNotFoundError,
    authorise_handover,
    list_handover_readiness_weights,
    set_handover_readiness_weight,
)

router = APIRouter(tags=["development"])


def _get_org_development(db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID) -> Development:
    dev = (
        db.query(Development)
        .filter(Development.id == development_id, Development.organisation_id == organisation_id)
        .first()
    )
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Development not found")
    return dev


@router.get("/api/v1/developments/{development_id}/handover-readiness", response_model=HandoverReadinessOut)
def get_handover_readiness(
    development_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_development(db, ctx.organisation_id, development_id)
    score_pct, checks = compute_handover_readiness(db, ctx.organisation_id, development_id)
    return HandoverReadinessOut(
        development_id=development_id,
        score_pct=score_pct,
        threshold_pct=HANDOVER_READINESS_THRESHOLD_PCT,
        ready=score_pct >= HANDOVER_READINESS_THRESHOLD_PCT,
        checks=[
            HandoverCheckOut(
                check_code=c.check_code,
                label=c.label,
                weight=c.weight,
                applicable_count=c.applicable_count,
                failing_count=c.failing_count,
                pass_ratio=round(c.pass_ratio, 3),
                missing_items=c.missing_items,
            )
            for c in checks
        ],
        missing=[item for c in checks for item in c.missing_items],
    )


@router.post("/api/v1/developments/{development_id}/handover/authorise", response_model=list[HandoverRecordOut])
def authorise_handover_endpoint(
    development_id: uuid.UUID,
    payload: AuthoriseHandoverRequest,
    ctx: AuthContext = Depends(require_permission("development.handover")),
    db: Session = Depends(get_db),
):
    development = _get_org_development(db, ctx.organisation_id, development_id)
    try:
        records = authorise_handover(
            db,
            ctx.organisation_id,
            development,
            override_reason=payload.override_reason,
            actor_user_id=ctx.user.id,
        )
    except HandoverNotReadyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    for record in records:
        db.refresh(record)
    return records


@router.get("/api/v1/developments/{development_id}/handover-records", response_model=list[HandoverRecordOut])
def list_handover_records(
    development_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_development(db, ctx.organisation_id, development_id)
    return (
        db.query(HandoverRecord)
        .filter(HandoverRecord.organisation_id == ctx.organisation_id, HandoverRecord.development_id == development_id)
        .order_by(HandoverRecord.created_at.desc())
        .all()
    )


@router.get("/api/v1/handover-readiness-weights", response_model=list[HandoverReadinessWeightOut])
def get_handover_readiness_weights(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    weights = list_handover_readiness_weights(db, ctx.organisation_id)
    return [
        HandoverReadinessWeightOut(check_code=w.check_code, label=CHECK_LABELS.get(w.check_code, w.check_code), weight=w.weight)
        for w in weights
    ]


@router.patch("/api/v1/handover-readiness-weights/{check_code}", response_model=HandoverReadinessWeightOut)
def update_handover_readiness_weight(
    check_code: str,
    payload: UpdateHandoverReadinessWeightRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        row = set_handover_readiness_weight(db, ctx.organisation_id, check_code, payload.weight)
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(row)
    return HandoverReadinessWeightOut(check_code=row.check_code, label=CHECK_LABELS.get(row.check_code, row.check_code), weight=row.weight)
