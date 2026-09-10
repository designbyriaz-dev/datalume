"""Developments, buildings, floors, and the composed hierarchy view —
architecture/03-development-domain.md §1. Kept separate from
router.py (properties/spaces) since these are three more resources at
different URL prefixes, not because the module boundary differs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.provenance import SourceType
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.development.golden_thread import get_golden_thread
from app.development.models import Building, Development, Floor, Property
from app.development.presenters import building_to_out, buildings_to_out, development_to_out, developments_to_out
from app.development.schemas import (
    BuildingHierarchyOut,
    BuildingOut,
    CreateBuildingRequest,
    CreateDevelopmentRequest,
    CreateFloorRequest,
    DevelopmentHierarchyOut,
    DevelopmentOut,
    FloorOut,
    FloorSummary,
    GoldenThreadOut,
)
from app.development.service import (
    HierarchyNotFoundError,
    create_building,
    create_development,
    create_floor,
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


def _get_org_building(db: Session, organisation_id: uuid.UUID, building_id: uuid.UUID) -> Building:
    building = (
        db.query(Building)
        .filter(Building.id == building_id, Building.organisation_id == organisation_id)
        .first()
    )
    if building is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Building not found")
    return building


# --- Developments -----------------------------------------------------


@router.post("/api/v1/developments", response_model=DevelopmentOut, status_code=status.HTTP_201_CREATED)
def add_development(
    payload: CreateDevelopmentRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    dev = create_development(
        db,
        ctx.organisation_id,
        name=payload.name,
        description=payload.description,
        address=payload.address,
        postcode=payload.postcode,
        number_of_planned_properties=payload.number_of_planned_properties,
        planning_reference=payload.planning_reference,
        building_control_reference=payload.building_control_reference,
        bsr_reference=payload.bsr_reference,
        source_type=SourceType.MANUAL,
        actor_user_id=ctx.user.id,
    )
    db.commit()
    db.refresh(dev)
    return development_to_out(db, ctx.organisation_id, dev)


@router.get("/api/v1/developments", response_model=list[DevelopmentOut])
def list_developments(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    developments = (
        db.query(Development)
        .filter(Development.organisation_id == ctx.organisation_id)
        .order_by(Development.created_at.desc())
        .all()
    )
    return developments_to_out(db, ctx.organisation_id, developments)


@router.get("/api/v1/developments/{development_id}", response_model=DevelopmentOut)
def get_development(
    development_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    dev = _get_org_development(db, ctx.organisation_id, development_id)
    return development_to_out(db, ctx.organisation_id, dev)


@router.get("/api/v1/developments/{development_id}/hierarchy", response_model=DevelopmentHierarchyOut)
def get_development_hierarchy(
    development_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """The composed tree: development -> buildings -> floors, with a
    property count at every level, including properties linked at a
    level but not fully drilled down (e.g. linked to the development
    directly, no building assigned yet)."""
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    dev = _get_org_development(db, ctx.organisation_id, development_id)

    buildings = db.query(Building).filter(Building.development_id == dev.id).order_by(Building.name).all()
    building_summaries = []
    for building in buildings:
        floors = db.query(Floor).filter(Floor.building_id == building.id).order_by(Floor.level_index).all()
        floor_summaries = [
            FloorSummary(
                id=floor.id,
                name=floor.name,
                level_index=floor.level_index,
                property_count=db.query(Property).filter(Property.floor_id == floor.id).count(),
            )
            for floor in floors
        ]
        unfloored = (
            db.query(Property)
            .filter(Property.building_id == building.id, Property.floor_id.is_(None))
            .count()
        )
        building_summaries.append(
            BuildingHierarchyOut(
                id=building.id,
                building_reference=building.building_reference,
                name=building.name,
                status=building.status.value,
                floors=floor_summaries,
                unfloored_property_count=unfloored,
            )
        )

    unbuilt = (
        db.query(Property)
        .filter(Property.development_id == dev.id, Property.building_id.is_(None))
        .count()
    )

    return DevelopmentHierarchyOut(
        id=dev.id,
        development_reference=dev.development_reference,
        name=dev.name,
        status=dev.status.value,
        buildings=building_summaries,
        unbuilt_property_count=unbuilt,
    )


# --- Buildings ----------------------------------------------------------


@router.post("/api/v1/buildings", response_model=BuildingOut, status_code=status.HTTP_201_CREATED)
def add_building(
    payload: CreateBuildingRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        building = create_building(
            db,
            ctx.organisation_id,
            name=payload.name,
            development_id=payload.development_id,
            building_type=payload.building_type,
            address=payload.address,
            storeys=payload.storeys,
            building_control_reference=payload.building_control_reference,
            bsr_reference=payload.bsr_reference,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(building)
    return building_to_out(db, ctx.organisation_id, building)


@router.get("/api/v1/buildings", response_model=list[BuildingOut])
def list_buildings(
    development_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Building).filter(Building.organisation_id == ctx.organisation_id)
    if development_id is not None:
        query = query.filter(Building.development_id == development_id)
    buildings = query.order_by(Building.created_at.desc()).all()
    return buildings_to_out(db, ctx.organisation_id, buildings)


@router.get("/api/v1/buildings/{building_id}", response_model=BuildingOut)
def get_building(
    building_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    building = _get_org_building(db, ctx.organisation_id, building_id)
    return building_to_out(db, ctx.organisation_id, building)


@router.get("/api/v1/buildings/{building_id}/golden-thread", response_model=GoldenThreadOut)
def get_building_golden_thread(
    building_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    building = _get_org_building(db, ctx.organisation_id, building_id)
    return get_golden_thread(db, ctx.organisation_id, building)


# --- Floors ---------------------------------------------------------------


@router.post("/api/v1/floors", response_model=FloorOut, status_code=status.HTTP_201_CREATED)
def add_floor(
    payload: CreateFloorRequest,
    ctx: AuthContext = Depends(require_permission("development.write")),
    db: Session = Depends(get_db),
):
    try:
        floor = create_floor(
            db,
            ctx.organisation_id,
            payload.building_id,
            name=payload.name,
            level_index=payload.level_index,
            source_type=SourceType.MANUAL,
            actor_user_id=ctx.user.id,
        )
    except HierarchyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(floor)
    return floor


@router.get("/api/v1/floors", response_model=list[FloorOut])
def list_floors(
    building_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    _get_org_building(db, ctx.organisation_id, building_id)
    return db.query(Floor).filter(Floor.building_id == building_id).order_by(Floor.level_index).all()
