"""ORM object -> *Out schema construction for development-domain entities.

Needed because external identifiers (UPRN, planning reference, building
control reference, BSR reference) are no longer columns on these models
as of Sprint 7 — they live in app.identifiers.models.ExternalReference —
so a plain `response_model=X` auto-serialize (from_attributes=True)
can't produce them; each entity has to be paired with a lookup.
list_properties_out/etc. use the bulk lookup (one query) rather than one
per row.
"""

import uuid

from sqlalchemy.orm import Session

from app.development.models import Building, Development, Property
from app.development.schemas import BuildingOut, DevelopmentOut, PropertyOut
from app.identifiers.service import get_external_references, get_external_references_bulk


def development_to_out(db: Session, organisation_id: uuid.UUID, dev: Development) -> DevelopmentOut:
    refs = get_external_references(db, organisation_id, "development", dev.id)
    return DevelopmentOut(
        id=dev.id,
        development_reference=dev.development_reference,
        name=dev.name,
        description=dev.description,
        address=dev.address,
        postcode=dev.postcode,
        status=dev.status.value,
        planning_reference=refs.get("PLANNING_REFERENCE"),
        building_control_reference=refs.get("BUILDING_CONTROL_REFERENCE"),
        bsr_reference=refs.get("BSR_REFERENCE"),
        source_type=dev.source_type.value,
        created_at=dev.created_at,
    )


def building_to_out(db: Session, organisation_id: uuid.UUID, building: Building) -> BuildingOut:
    refs = get_external_references(db, organisation_id, "building", building.id)
    return BuildingOut(
        id=building.id,
        building_reference=building.building_reference,
        development_id=building.development_id,
        name=building.name,
        building_type=building.building_type,
        address=building.address,
        storeys=building.storeys,
        status=building.status.value,
        building_control_reference=refs.get("BUILDING_CONTROL_REFERENCE"),
        bsr_reference=refs.get("BSR_REFERENCE"),
        source_type=building.source_type.value,
        created_at=building.created_at,
    )


def property_to_out(db: Session, organisation_id: uuid.UUID, prop: Property) -> PropertyOut:
    refs = get_external_references(db, organisation_id, "property", prop.id)
    return PropertyOut(
        id=prop.id,
        property_reference=prop.property_reference,
        address=prop.address,
        postcode=prop.postcode,
        uprn=refs.get("UPRN"),
        property_type=prop.property_type,
        status=prop.status.value,
        development_id=prop.development_id,
        building_id=prop.building_id,
        floor_id=prop.floor_id,
        source_type=prop.source_type.value,
        source_dataset_id=prop.source_dataset_id,
        original_reference=prop.original_reference,
        created_at=prop.created_at,
    )


def properties_to_out(db: Session, organisation_id: uuid.UUID, properties: list[Property]) -> list[PropertyOut]:
    refs_by_id = get_external_references_bulk(db, organisation_id, "property", [p.id for p in properties])
    return [
        PropertyOut(
            id=p.id,
            property_reference=p.property_reference,
            address=p.address,
            postcode=p.postcode,
            uprn=refs_by_id.get(str(p.id), {}).get("UPRN"),
            property_type=p.property_type,
            status=p.status.value,
            development_id=p.development_id,
            building_id=p.building_id,
            floor_id=p.floor_id,
            source_type=p.source_type.value,
            source_dataset_id=p.source_dataset_id,
            original_reference=p.original_reference,
            created_at=p.created_at,
        )
        for p in properties
    ]


def developments_to_out(db: Session, organisation_id: uuid.UUID, developments: list[Development]) -> list[DevelopmentOut]:
    refs_by_id = get_external_references_bulk(db, organisation_id, "development", [d.id for d in developments])
    return [
        DevelopmentOut(
            id=d.id,
            development_reference=d.development_reference,
            name=d.name,
            description=d.description,
            address=d.address,
            postcode=d.postcode,
            status=d.status.value,
            planning_reference=refs_by_id.get(str(d.id), {}).get("PLANNING_REFERENCE"),
            building_control_reference=refs_by_id.get(str(d.id), {}).get("BUILDING_CONTROL_REFERENCE"),
            bsr_reference=refs_by_id.get(str(d.id), {}).get("BSR_REFERENCE"),
            source_type=d.source_type.value,
            created_at=d.created_at,
        )
        for d in developments
    ]


def buildings_to_out(db: Session, organisation_id: uuid.UUID, buildings: list[Building]) -> list[BuildingOut]:
    refs_by_id = get_external_references_bulk(db, organisation_id, "building", [b.id for b in buildings])
    return [
        BuildingOut(
            id=b.id,
            building_reference=b.building_reference,
            development_id=b.development_id,
            name=b.name,
            building_type=b.building_type,
            address=b.address,
            storeys=b.storeys,
            status=b.status.value,
            building_control_reference=refs_by_id.get(str(b.id), {}).get("BUILDING_CONTROL_REFERENCE"),
            bsr_reference=refs_by_id.get(str(b.id), {}).get("BSR_REFERENCE"),
            source_type=b.source_type.value,
            created_at=b.created_at,
        )
        for b in buildings
    ]
