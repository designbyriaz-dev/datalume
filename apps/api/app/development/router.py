import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.models import Property, Space
from app.development.presenters import properties_to_out, property_to_out
from app.development.property_360 import get_property_360
from app.development.schemas import (
    CreatePropertyRequest,
    CreateSpaceRequest,
    Property360Out,
    PropertyOut,
    SpaceOut,
    UpdatePropertyStatusRequest,
)
from app.development.service import (
    HierarchyMismatchError,
    HierarchyNotFoundError,
    create_property,
    create_space,
    update_property_status,
)

router = APIRouter(prefix="/api/v1/properties", tags=["development"])


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = (
        db.query(Property)
        .filter(Property.id == property_id, Property.organisation_id == organisation_id)
        .first()
    )
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    return prop


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def add_property(
    payload: CreatePropertyRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        prop = create_property(
            db,
            ctx.organisation_id,
            address=payload.address,
            postcode=payload.postcode,
            uprn=payload.uprn,
            property_type=payload.property_type,
            status=payload.status,
            development_id=payload.development_id,
            building_id=payload.building_id,
            floor_id=payload.floor_id,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(prop)
    return property_to_out(db, ctx.organisation_id, prop)


@router.get("", response_model=list[PropertyOut])
def list_properties(
    limit: int = 100,
    offset: int = 0,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Property).filter(Property.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(Property.development_id == development_id)
    if building_id is not None:
        query = query.filter(Property.building_id == building_id)
    properties = query.order_by(Property.created_at.desc()).offset(offset).limit(min(limit, 500)).all()
    return properties_to_out(db, ctx.organisation_id, properties)


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(
    property_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    prop = _get_org_property(db, ctx.organisation_id, property_id)
    return property_to_out(db, ctx.organisation_id, prop)


@router.get("/{property_id}/360", response_model=Property360Out)
def get_property_360_endpoint(
    property_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    prop = _get_org_property(db, ctx.organisation_id, property_id)
    view = get_property_360(db, ctx.organisation_id, prop)
    db.commit()  # Data Health findings recomputed on read, same as GET /api/v1/data-health
    return view


@router.post("/{property_id}/status", response_model=PropertyOut)
def update_property_status_endpoint(
    property_id: uuid.UUID,
    payload: UpdatePropertyStatusRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    prop = _get_org_property(db, ctx.organisation_id, property_id)
    try:
        update_property_status(db, ctx.organisation_id, prop, new_status=payload.status, actor_user_id=ctx.user.id)
    except HierarchyMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(prop)
    return property_to_out(db, ctx.organisation_id, prop)


@router.post("/{property_id}/spaces", response_model=SpaceOut, status_code=status.HTTP_201_CREATED)
def add_space(
    property_id: uuid.UUID,
    payload: CreateSpaceRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    _get_org_property(db, ctx.organisation_id, property_id)  # 404s if missing/cross-org
    space = create_space(
        db,
        ctx.organisation_id,
        name=payload.name,
        property_id=property_id,
        space_type=payload.space_type,
        actor_user_id=ctx.user.id,
    )
    db.commit()
    db.refresh(space)
    return space


@router.get("/{property_id}/spaces", response_model=list[SpaceOut])
def list_spaces(
    property_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_property(db, ctx.organisation_id, property_id)
    return db.query(Space).filter(Space.property_id == property_id).order_by(Space.name).all()
