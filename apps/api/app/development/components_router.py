"""Component register — architecture/03-development-domain.md §2.
Kept separate from router.py/hierarchy_router.py for the same reason
those two are separate from each other: a different set of URL prefixes,
not a different module boundary."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.component_types import ensure_component_type_catalog_seeded
from app.development.models import Component, ComponentType
from app.development.presenters import component_to_out, components_to_out
from app.development.schemas import ComponentOut, ComponentTypeOut, CreateComponentRequest
from app.development.service import HierarchyMismatchError, HierarchyNotFoundError, create_component

router = APIRouter(tags=["development"])


def _get_org_component(db: Session, organisation_id: uuid.UUID, component_id: uuid.UUID) -> Component:
    component = (
        db.query(Component)
        .filter(Component.id == component_id, Component.organisation_id == organisation_id)
        .first()
    )
    if component is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Component not found")
    return component


@router.get("/api/v1/component-types", response_model=list[ComponentTypeOut])
def list_component_types(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    ensure_component_type_catalog_seeded(db)
    db.commit()
    return (
        db.query(ComponentType)
        .filter((ComponentType.organisation_id == ctx.organisation_id) | (ComponentType.organisation_id.is_(None)))
        .order_by(ComponentType.name)
        .all()
    )


@router.post("/api/v1/components", response_model=ComponentOut, status_code=status.HTTP_201_CREATED)
def add_component(
    payload: CreateComponentRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        component = create_component(
            db,
            ctx.organisation_id,
            component_type_id=payload.component_type_id,
            component_subtype=payload.component_subtype,
            manufacturer=payload.manufacturer,
            model=payload.model,
            serial_number=payload.serial_number,
            installer=payload.installer,
            installation_date=payload.installation_date,
            commissioning_date=payload.commissioning_date,
            warranty_start=payload.warranty_start,
            warranty_expiry=payload.warranty_expiry,
            expected_life_years=payload.expected_life_years,
            status=payload.status,
            development_id=payload.development_id,
            building_id=payload.building_id,
            property_id=payload.property_id,
            space_id=payload.space_id,
            parent_component_id=payload.parent_component_id,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(component)
    return component_to_out(db, ctx.organisation_id, component)


@router.get("/api/v1/components", response_model=list[ComponentOut])
def list_components(
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    space_id: uuid.UUID | None = None,
    parent_component_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Component).filter(Component.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(Component.development_id == development_id)
    if building_id is not None:
        query = query.filter(Component.building_id == building_id)
    if property_id is not None:
        query = query.filter(Component.property_id == property_id)
    if space_id is not None:
        query = query.filter(Component.space_id == space_id)
    if parent_component_id is not None:
        query = query.filter(Component.parent_component_id == parent_component_id)
    components = query.order_by(Component.created_at.desc()).offset(offset).limit(min(limit, 500)).all()
    return components_to_out(db, ctx.organisation_id, components)


@router.get("/api/v1/components/{component_id}", response_model=ComponentOut)
def get_component(
    component_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    component = _get_org_component(db, ctx.organisation_id, component_id)
    return component_to_out(db, ctx.organisation_id, component)


@router.get("/api/v1/components/{component_id}/children", response_model=list[ComponentOut])
def list_component_children(
    component_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_component(db, ctx.organisation_id, component_id)
    children = (
        db.query(Component)
        .filter(Component.parent_component_id == component_id, Component.organisation_id == ctx.organisation_id)
        .order_by(Component.created_at)
        .all()
    )
    return components_to_out(db, ctx.organisation_id, children)
