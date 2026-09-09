"""Shared create-entity service functions — architecture/02-data-platform.md
§3: "manual entry and file import produce identical, equally valid
records" because both call the same function here. app/development/router.py
(manual "+Add") and app/development/importers.py (the ingestion
IMPORTERS["PROPERTIES"] registration) are both thin callers — neither
duplicates the other's logic.

resolve_property_hierarchy is the one non-obvious piece: a property can
be linked at any level (development/building/floor), and those levels
must be internally consistent (a floor's building must match a given
building_id; a building's development must match a given development_id)
— rather than trusting the caller, the parent is always derived from the
most specific level given and cross-checked against anything else
supplied.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Building, Development, Floor, Property, PropertyStatus, Space
from app.development.reference import (
    next_building_reference,
    next_development_reference,
    next_property_reference,
)
from app.platform.audit import record_audit_event


class HierarchyNotFoundError(ValueError):
    """A given development_id/building_id/floor_id doesn't exist in this
    organisation — the router maps this to a 404."""


class HierarchyMismatchError(ValueError):
    """Two given hierarchy ids are inconsistent (e.g. a floor_id whose
    building doesn't match the given building_id) — the router maps this
    to a 400."""


def _get_org_development(db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID) -> Development:
    dev = (
        db.query(Development)
        .filter(Development.id == development_id, Development.organisation_id == organisation_id)
        .first()
    )
    if dev is None:
        raise HierarchyNotFoundError(f"Development {development_id} not found")
    return dev


def _get_org_building(db: Session, organisation_id: uuid.UUID, building_id: uuid.UUID) -> Building:
    building = (
        db.query(Building)
        .filter(Building.id == building_id, Building.organisation_id == organisation_id)
        .first()
    )
    if building is None:
        raise HierarchyNotFoundError(f"Building {building_id} not found")
    return building


def _get_org_floor(db: Session, organisation_id: uuid.UUID, floor_id: uuid.UUID) -> Floor:
    floor = db.query(Floor).filter(Floor.id == floor_id, Floor.organisation_id == organisation_id).first()
    if floor is None:
        raise HierarchyNotFoundError(f"Floor {floor_id} not found")
    return floor


def resolve_property_hierarchy(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    development_id: uuid.UUID | None,
    building_id: uuid.UUID | None,
    floor_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    if floor_id is not None:
        floor = _get_org_floor(db, organisation_id, floor_id)
        if building_id is not None and building_id != floor.building_id:
            raise HierarchyMismatchError("floor_id does not belong to the given building_id")
        building_id = floor.building_id

    if building_id is not None:
        building = _get_org_building(db, organisation_id, building_id)
        if building.development_id is not None:
            if development_id is not None and development_id != building.development_id:
                raise HierarchyMismatchError("building_id does not belong to the given development_id")
            development_id = building.development_id

    if development_id is not None:
        _get_org_development(db, organisation_id, development_id)  # existence/ownership check only

    return development_id, building_id, floor_id


def create_development(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    address: str | None = None,
    postcode: str | None = None,
    planning_reference: str | None = None,
    building_control_reference: str | None = None,
    bsr_reference: str | None = None,
    source_type: SourceType = SourceType.MANUAL,
    actor_user_id: uuid.UUID | None = None,
) -> Development:
    dev = Development(
        organisation_id=organisation_id,
        development_reference=next_development_reference(db, organisation_id),
        name=name,
        description=description,
        address=address,
        postcode=postcode,
        planning_reference=planning_reference,
        building_control_reference=building_control_reference,
        bsr_reference=bsr_reference,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(dev)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="development.created",
        entity_type="development",
        entity_id=str(dev.id),
        after={"development_reference": dev.development_reference, "name": name},
    )
    return dev


def create_building(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    name: str,
    development_id: uuid.UUID | None = None,
    building_type: str | None = None,
    address: str | None = None,
    storeys: int | None = None,
    building_control_reference: str | None = None,
    bsr_reference: str | None = None,
    source_type: SourceType = SourceType.MANUAL,
    actor_user_id: uuid.UUID | None = None,
) -> Building:
    if development_id is not None:
        _get_org_development(db, organisation_id, development_id)

    building = Building(
        organisation_id=organisation_id,
        development_id=development_id,
        building_reference=next_building_reference(db, organisation_id),
        name=name,
        building_type=building_type,
        address=address,
        storeys=storeys,
        building_control_reference=building_control_reference,
        bsr_reference=bsr_reference,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(building)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="building.created",
        entity_type="building",
        entity_id=str(building.id),
        after={"building_reference": building.building_reference, "name": name},
    )
    return building


def create_floor(
    db: Session,
    organisation_id: uuid.UUID,
    building_id: uuid.UUID,
    *,
    name: str,
    level_index: int | None = None,
    source_type: SourceType = SourceType.MANUAL,
    actor_user_id: uuid.UUID | None = None,
) -> Floor:
    _get_org_building(db, organisation_id, building_id)

    floor = Floor(
        organisation_id=organisation_id,
        building_id=building_id,
        name=name,
        level_index=level_index,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(floor)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="floor.created",
        entity_type="floor",
        entity_id=str(floor.id),
        after={"name": name, "building_id": str(building_id)},
    )
    return floor


def create_property(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    address: str,
    postcode: str | None = None,
    uprn: str | None = None,
    property_type: str | None = None,
    status: PropertyStatus = PropertyStatus.OPERATIONAL,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    floor_id: uuid.UUID | None = None,
    source_type: SourceType,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Property:
    development_id, building_id, floor_id = resolve_property_hierarchy(
        db, organisation_id, development_id=development_id, building_id=building_id, floor_id=floor_id
    )

    prop = Property(
        organisation_id=organisation_id,
        development_id=development_id,
        building_id=building_id,
        floor_id=floor_id,
        property_reference=next_property_reference(db, organisation_id),
        address=address,
        postcode=postcode,
        uprn=uprn,
        property_type=property_type,
        status=status,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(prop)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="property.created",
        entity_type="property",
        entity_id=str(prop.id),
        after={"property_reference": prop.property_reference, "address": address, "source_type": source_type.value},
    )
    return prop


def create_space(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    name: str,
    property_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    space_type: str | None = None,
    source_type: SourceType = SourceType.MANUAL,
    actor_user_id: uuid.UUID | None = None,
) -> Space:
    if property_id is None and building_id is None:
        raise HierarchyMismatchError("A space needs a property_id or a building_id")

    space = Space(
        organisation_id=organisation_id,
        property_id=property_id,
        building_id=building_id,
        name=name,
        space_type=space_type,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(space)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="space.created",
        entity_type="space",
        entity_id=str(space.id),
        after={"name": name, "property_id": str(property_id) if property_id else None},
    )
    return space
