"""Repairs — architecture/04-operations-domain.md §1-2, spec §43-44.
First router in the `app.operations` package — gated by the
`operations.*` permissions RBAC has carried since Sprint 1
(REPAIRS_MANAGER, PROPERTY_MANAGER, ASSET_MANAGER) but nothing has used
until now."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.operations.models import Repair
from app.operations.repairs_intelligence import get_repairs_intelligence
from app.operations.repeat_repair import component_model_trend, repeat_failures_for_component, repeat_repairs_for_property
from app.operations.schemas import (
    CreateRepairRequest,
    ModelTrendSignalOut,
    RepairOut,
    RepairRuleConfigOut,
    RepairsIntelligenceOut,
    RepeatFailureSignalOut,
    RepeatRepairSignalOut,
    UpdateRepairRuleConfigRequest,
    UpdateRepairStatusRequest,
)
from app.operations.service import (
    InvalidRepairTransitionError,
    RepairNotFoundError,
    create_repair,
    list_repair_rule_configs,
    set_repair_rule_config,
    update_repair_status,
)

router = APIRouter(tags=["operations"])


def _get_org_repair(db: Session, organisation_id: uuid.UUID, repair_id: uuid.UUID) -> Repair:
    repair = db.query(Repair).filter(Repair.id == repair_id, Repair.organisation_id == organisation_id).first()
    if repair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repair not found")
    return repair


@router.post("/api/v1/repairs", response_model=RepairOut, status_code=status.HTTP_201_CREATED)
def add_repair(
    payload: CreateRepairRequest,
    ctx: AuthContext = Depends(require_permission("operations.write")),
    db: Session = Depends(get_db),
):
    try:
        repair = create_repair(
            db,
            ctx.organisation_id,
            property_id=payload.property_id,
            component_id=payload.component_id,
            category=payload.category,
            description=payload.description,
            reported_date=payload.reported_date,
            priority=payload.priority,
            contractor=payload.contractor,
            cost_pence=payload.cost_pence,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except RepairNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(repair)
    return repair


@router.post("/api/v1/repairs/{repair_id}/status", response_model=RepairOut)
def update_repair_status_endpoint(
    repair_id: uuid.UUID,
    payload: UpdateRepairStatusRequest,
    ctx: AuthContext = Depends(require_permission("operations.write")),
    db: Session = Depends(get_db),
):
    repair = _get_org_repair(db, ctx.organisation_id, repair_id)
    try:
        update_repair_status(
            db,
            ctx.organisation_id,
            repair,
            new_status=payload.status,
            completed_date=payload.completed_date,
            cost_pence=payload.cost_pence,
            actor_user_id=ctx.user.id,
        )
    except InvalidRepairTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(repair)
    return repair


@router.get("/api/v1/repairs/intelligence", response_model=RepairsIntelligenceOut)
def repairs_intelligence(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return get_repairs_intelligence(db, ctx.organisation_id)


@router.get("/api/v1/repairs/model-trend", response_model=ModelTrendSignalOut | None)
def repairs_model_trend(
    component_type_id: uuid.UUID,
    manufacturer: str,
    model: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return component_model_trend(db, ctx.organisation_id, component_type_id, manufacturer, model)


@router.get("/api/v1/repairs", response_model=list[RepairOut])
def list_repairs(
    property_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    repair_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Repair).filter(Repair.organisation_id == ctx.organisation_id)
    if property_id is not None:
        query = query.filter(Repair.property_id == property_id)
    if component_id is not None:
        query = query.filter(Repair.component_id == component_id)
    if repair_status is not None:
        query = query.filter(Repair.status == repair_status)
    return query.order_by(Repair.reported_date.desc()).all()


@router.get("/api/v1/repairs/{repair_id}", response_model=RepairOut)
def get_repair(
    repair_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return _get_org_repair(db, ctx.organisation_id, repair_id)


@router.get("/api/v1/properties/{property_id}/repeat-repairs", response_model=RepeatRepairSignalOut | None)
def property_repeat_repairs(
    property_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return repeat_repairs_for_property(db, ctx.organisation_id, property_id)


@router.get("/api/v1/components/{component_id}/repeat-failures", response_model=RepeatFailureSignalOut | None)
def component_repeat_failures(
    component_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return repeat_failures_for_component(db, ctx.organisation_id, component_id)


@router.get("/api/v1/repair-rule-configs", response_model=list[RepairRuleConfigOut])
def get_repair_rule_configs(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_repair_rule_configs(db, ctx.organisation_id)


@router.patch("/api/v1/repair-rule-configs/{rule_code}", response_model=RepairRuleConfigOut)
def update_repair_rule_config(
    rule_code: str,
    payload: UpdateRepairRuleConfigRequest,
    ctx: AuthContext = Depends(require_permission("operations.write")),
    db: Session = Depends(get_db),
):
    try:
        config = set_repair_rule_config(
            db,
            ctx.organisation_id,
            rule_code,
            {
                "window_months": payload.window_months,
                "threshold": payload.threshold,
                "threshold_ratio": payload.threshold_ratio,
                "min_installed_base": payload.min_installed_base,
            },
        )
    except RepairNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(config)
    return config
