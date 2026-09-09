"""Hazards, damp & mould — architecture/04-operations-domain.md §5, spec
§49. Gated by `operations.compliance` for writes — hazards (especially
HHSRS-category ones) are the same safety-critical territory as the
compliance framework itself, held by COMPLIANCE_MANAGER and
BUILDING_SAFETY_MANAGER, not the broader operations.write REPAIRS_
MANAGER/PROPERTY_MANAGER also hold."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.operations.hazards.models import Hazard, HazardAction
from app.operations.hazards.repeat_hazard import repeat_hazards_for_property
from app.operations.hazards.schemas import (
    CreateHazardActionRequest,
    CreateHazardRequest,
    HazardActionOut,
    HazardOut,
    HazardRuleConfigOut,
    RepeatHazardSignalOut,
    UpdateHazardActionStatusRequest,
    UpdateHazardRuleConfigRequest,
    UpdateHazardStatusRequest,
)
from app.operations.hazards.service import (
    HazardNotFoundError,
    InvalidHazardActionTransitionError,
    InvalidHazardTransitionError,
    create_hazard,
    create_hazard_action,
    list_hazard_rule_configs,
    set_hazard_rule_config,
    update_hazard_action_status,
    update_hazard_status,
)

router = APIRouter(prefix="/api/v1", tags=["hazards"])


def _get_org_hazard(db: Session, organisation_id: uuid.UUID, hazard_id: uuid.UUID) -> Hazard:
    hazard = db.query(Hazard).filter(Hazard.id == hazard_id, Hazard.organisation_id == organisation_id).first()
    if hazard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hazard not found")
    return hazard


def _get_org_hazard_action(db: Session, organisation_id: uuid.UUID, action_id: uuid.UUID) -> HazardAction:
    action = (
        db.query(HazardAction).filter(HazardAction.id == action_id, HazardAction.organisation_id == organisation_id).first()
    )
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hazard action not found")
    return action


@router.post("/hazards", response_model=HazardOut, status_code=status.HTTP_201_CREATED)
def add_hazard(
    payload: CreateHazardRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        hazard = create_hazard(
            db,
            ctx.organisation_id,
            property_id=payload.property_id,
            hazard_type=payload.hazard_type,
            reported_date=payload.reported_date,
            severity=payload.severity,
            actor_user_id=ctx.user.id,
        )
    except HazardNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(hazard)
    return hazard


@router.get("/hazards", response_model=list[HazardOut])
def list_hazards(
    property_id: uuid.UUID | None = None,
    hazard_type: str | None = None,
    hazard_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Hazard).filter(Hazard.organisation_id == ctx.organisation_id)
    if property_id is not None:
        query = query.filter(Hazard.property_id == property_id)
    if hazard_type is not None:
        query = query.filter(Hazard.hazard_type == hazard_type)
    if hazard_status is not None:
        query = query.filter(Hazard.status == hazard_status)
    return query.order_by(Hazard.reported_date.desc()).all()


@router.get("/hazards/{hazard_id}", response_model=HazardOut)
def get_hazard(
    hazard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return _get_org_hazard(db, ctx.organisation_id, hazard_id)


@router.post("/hazards/{hazard_id}/status", response_model=HazardOut)
def update_hazard_status_endpoint(
    hazard_id: uuid.UUID,
    payload: UpdateHazardStatusRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    hazard = _get_org_hazard(db, ctx.organisation_id, hazard_id)
    try:
        update_hazard_status(
            db,
            ctx.organisation_id,
            hazard,
            new_status=payload.status,
            investigation_status=payload.investigation_status,
            findings=payload.findings,
            deadline=payload.deadline,
            actor_user_id=ctx.user.id,
        )
    except InvalidHazardTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(hazard)
    return hazard


@router.post("/hazards/{hazard_id}/actions", response_model=HazardActionOut, status_code=status.HTTP_201_CREATED)
def add_hazard_action(
    hazard_id: uuid.UUID,
    payload: CreateHazardActionRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    hazard = _get_org_hazard(db, ctx.organisation_id, hazard_id)
    try:
        action = create_hazard_action(
            db,
            ctx.organisation_id,
            hazard,
            description=payload.description,
            deadline=payload.deadline,
            evidence_document_id=payload.evidence_document_id,
            actor_user_id=ctx.user.id,
        )
    except HazardNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(action)
    return action


@router.get("/hazards/{hazard_id}/actions", response_model=list[HazardActionOut])
def get_hazard_actions(
    hazard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_hazard(db, ctx.organisation_id, hazard_id)
    return (
        db.query(HazardAction)
        .filter(HazardAction.organisation_id == ctx.organisation_id, HazardAction.hazard_id == hazard_id)
        .order_by(HazardAction.deadline)
        .all()
    )


@router.post("/hazard-actions/{action_id}/status", response_model=HazardActionOut)
def update_hazard_action_status_endpoint(
    action_id: uuid.UUID,
    payload: UpdateHazardActionStatusRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    action = _get_org_hazard_action(db, ctx.organisation_id, action_id)
    try:
        update_hazard_action_status(
            db,
            ctx.organisation_id,
            action,
            new_status=payload.status,
            completed_date=payload.completed_date,
            evidence_document_id=payload.evidence_document_id,
            actor_user_id=ctx.user.id,
        )
    except InvalidHazardActionTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except HazardNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(action)
    return action


@router.get("/properties/{property_id}/repeat-hazards", response_model=RepeatHazardSignalOut | None)
def property_repeat_hazards(
    property_id: uuid.UUID,
    hazard_type: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return repeat_hazards_for_property(db, ctx.organisation_id, property_id, hazard_type)


@router.get("/hazard-rule-configs", response_model=list[HazardRuleConfigOut])
def get_hazard_rule_configs(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_hazard_rule_configs(db, ctx.organisation_id)


@router.patch("/hazard-rule-configs/{rule_code}", response_model=HazardRuleConfigOut)
def update_hazard_rule_config(
    rule_code: str,
    payload: UpdateHazardRuleConfigRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        config = set_hazard_rule_config(
            db, ctx.organisation_id, rule_code, {"window_months": payload.window_months, "threshold": payload.threshold}
        )
    except HazardNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(config)
    return config
