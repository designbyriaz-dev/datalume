"""Planned Investment — architecture/03-development-domain.md §6, spec
§40. Reads are open to any authenticated org member (`operations.read`
would be the natural gate, but this composes Component data too, so it
follows Property 360/Golden Thread's precedent of no extra permission
beyond being a member); weight/config writes are gated the same way
Handover Readiness's weights are — `development.write`, since this is
reshaping how the Component register's own lifecycle data gets scored,
not a day-to-day operational write."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.models import Component
from app.development.planned_investment import compute_investment_priority, list_planned_investment
from app.development.schemas import (
    PlannedInvestmentConfigOut,
    PlannedInvestmentScoreOut,
    PlannedInvestmentWeightOut,
    UpdatePlannedInvestmentConfigRequest,
    UpdatePlannedInvestmentWeightRequest,
)
from app.development.service import (
    HierarchyNotFoundError,
    get_or_create_planned_investment_config,
    list_planned_investment_weights,
    set_planned_investment_config,
    set_planned_investment_weight,
)

router = APIRouter(tags=["development"])


def _get_org_component(db: Session, organisation_id: uuid.UUID, component_id: uuid.UUID) -> Component:
    component = (
        db.query(Component).filter(Component.id == component_id, Component.organisation_id == organisation_id).first()
    )
    if component is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Component not found")
    return component


@router.get("/api/v1/components/{component_id}/planned-investment", response_model=PlannedInvestmentScoreOut)
def get_component_planned_investment(
    component_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    component = _get_org_component(db, ctx.organisation_id, component_id)
    from app.development.composition import component_type_names_for

    type_name = component_type_names_for(db, [component]).get(component.component_type_id, "Unknown")
    return compute_investment_priority(db, ctx.organisation_id, component, type_name)


@router.get("/api/v1/planned-investment", response_model=list[PlannedInvestmentScoreOut])
def get_planned_investment_list(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_planned_investment(
        db, ctx.organisation_id, development_id=development_id, building_id=building_id, property_id=property_id
    )


@router.get("/api/v1/planned-investment-weights", response_model=list[PlannedInvestmentWeightOut])
def get_planned_investment_weights(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    from app.development.planned_investment import FACTOR_LABELS

    weights = list_planned_investment_weights(db, ctx.organisation_id)
    return [
        PlannedInvestmentWeightOut(factor_code=w.factor_code, label=FACTOR_LABELS[w.factor_code], weight=w.weight)
        for w in weights
    ]


@router.patch("/api/v1/planned-investment-weights/{factor_code}", response_model=PlannedInvestmentWeightOut)
def update_planned_investment_weight(
    factor_code: str,
    payload: UpdatePlannedInvestmentWeightRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    from app.development.planned_investment import FACTOR_LABELS

    try:
        row = set_planned_investment_weight(db, ctx.organisation_id, factor_code, payload.weight)
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(row)
    return PlannedInvestmentWeightOut(factor_code=row.factor_code, label=FACTOR_LABELS[row.factor_code], weight=row.weight)


@router.get("/api/v1/planned-investment-config", response_model=PlannedInvestmentConfigOut)
def get_planned_investment_config(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    config = get_or_create_planned_investment_config(db, ctx.organisation_id)
    db.commit()
    db.refresh(config)
    return config


@router.patch("/api/v1/planned-investment-config", response_model=PlannedInvestmentConfigOut)
def update_planned_investment_config(
    payload: UpdatePlannedInvestmentConfigRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    config = set_planned_investment_config(
        db,
        ctx.organisation_id,
        repair_frequency_window_months=payload.repair_frequency_window_months,
        repair_frequency_threshold=payload.repair_frequency_threshold,
    )
    db.commit()
    db.refresh(config)
    return config
