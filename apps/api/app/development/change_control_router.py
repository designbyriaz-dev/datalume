"""Change Control register — architecture/03-development-domain.md §7,
spec §33. Kept separate from specifications_router.py for the same
reason components_router.py is separate from hierarchy_router.py: a
different URL prefix, not a different module boundary — though the two
are tightly coupled (a change control always targets a specification)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.models import ChangeControl
from app.development.presenters import change_control_to_out, changes_to_out
from app.development.schemas import ApproveChangeControlRequest, ChangeControlOut, SubmitChangeControlRequest
from app.development.service import (
    HierarchyMismatchError,
    HierarchyNotFoundError,
    InvalidChangeControlTransitionError,
    approve_change_control,
    cancel_change_control,
    implement_change_control,
    reject_change_control,
    start_change_control_review,
    submit_change_control,
)

router = APIRouter(tags=["development"])


def _get_org_change_control(db: Session, organisation_id: uuid.UUID, change_control_id: uuid.UUID) -> ChangeControl:
    change = (
        db.query(ChangeControl)
        .filter(ChangeControl.id == change_control_id, ChangeControl.organisation_id == organisation_id)
        .first()
    )
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change control not found")
    return change


@router.post("/api/v1/change-control", response_model=ChangeControlOut, status_code=status.HTTP_201_CREATED)
def add_change_control(
    payload: SubmitChangeControlRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        change = submit_change_control(
            db,
            ctx.organisation_id,
            specification_id=payload.specification_id,
            proposed_value=payload.proposed_value,
            reason=payload.reason,
            impact_description=payload.impact_description,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.post("/api/v1/change-control/{change_control_id}/start-review", response_model=ChangeControlOut)
def start_review_endpoint(
    change_control_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    try:
        start_change_control_review(db, ctx.organisation_id, change, actor_user_id=ctx.user.id)
    except InvalidChangeControlTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.post("/api/v1/change-control/{change_control_id}/approve", response_model=ChangeControlOut)
def approve_endpoint(
    change_control_id: uuid.UUID,
    payload: ApproveChangeControlRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    try:
        approve_change_control(
            db,
            ctx.organisation_id,
            change,
            external_approval_reference=payload.external_approval_reference,
            actor_user_id=ctx.user.id,
        )
    except InvalidChangeControlTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.post("/api/v1/change-control/{change_control_id}/reject", response_model=ChangeControlOut)
def reject_endpoint(
    change_control_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    try:
        reject_change_control(db, ctx.organisation_id, change, actor_user_id=ctx.user.id)
    except InvalidChangeControlTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.post("/api/v1/change-control/{change_control_id}/cancel", response_model=ChangeControlOut)
def cancel_endpoint(
    change_control_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    try:
        cancel_change_control(db, ctx.organisation_id, change, actor_user_id=ctx.user.id)
    except InvalidChangeControlTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.post("/api/v1/change-control/{change_control_id}/implement", response_model=ChangeControlOut)
def implement_endpoint(
    change_control_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    try:
        implement_change_control(db, ctx.organisation_id, change, actor_user_id=ctx.user.id)
    except InvalidChangeControlTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(change)
    return change_control_to_out(db, ctx.organisation_id, change)


@router.get("/api/v1/change-control", response_model=list[ChangeControlOut])
def list_change_control(
    specification_id: uuid.UUID | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    change_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(ChangeControl).filter(ChangeControl.organisation_id == ctx.organisation_id)
    if specification_id:
        query = query.filter(ChangeControl.specification_id == specification_id)
    if related_entity_type:
        query = query.filter(ChangeControl.related_entity_type == related_entity_type)
    if related_entity_id:
        query = query.filter(ChangeControl.related_entity_id == related_entity_id)
    if change_status:
        query = query.filter(ChangeControl.status == change_status)
    changes = query.order_by(ChangeControl.created_at.desc()).all()
    return changes_to_out(db, ctx.organisation_id, changes)


@router.get("/api/v1/change-control/{change_control_id}", response_model=ChangeControlOut)
def get_change_control(
    change_control_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    change = _get_org_change_control(db, ctx.organisation_id, change_control_id)
    return change_control_to_out(db, ctx.organisation_id, change)
