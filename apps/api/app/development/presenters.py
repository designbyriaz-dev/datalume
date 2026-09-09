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
from datetime import date

from sqlalchemy.orm import Session

from app.development.models import Building, ChangeControl, Component, ComponentType, Development, Property, Warranty
from app.development.schemas import BuildingOut, ChangeControlOut, ComponentOut, DevelopmentOut, PropertyOut, WarrantyOut
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


def component_to_out(db: Session, organisation_id: uuid.UUID, component: Component) -> ComponentOut:
    refs = get_external_references(db, organisation_id, "component", component.id)
    component_type = db.get(ComponentType, component.component_type_id)
    return ComponentOut(
        id=component.id,
        component_reference=component.component_reference,
        component_type_id=component.component_type_id,
        component_type_name=component_type.name if component_type else "Unknown",
        component_subtype=component.component_subtype,
        manufacturer=component.manufacturer,
        model=component.model,
        serial_number=refs.get("MANUFACTURER_SERIAL_NUMBER"),
        installer=component.installer,
        installation_date=component.installation_date,
        commissioning_date=component.commissioning_date,
        warranty_start=component.warranty_start,
        warranty_expiry=component.warranty_expiry,
        expected_life_years=component.expected_life_years,
        indicative_replacement_date=component.indicative_replacement_date,
        status=component.status.value,
        development_id=component.development_id,
        building_id=component.building_id,
        property_id=component.property_id,
        space_id=component.space_id,
        parent_component_id=component.parent_component_id,
        source_type=component.source_type.value,
        source_dataset_id=component.source_dataset_id,
        original_reference=component.original_reference,
        created_at=component.created_at,
    )


def components_to_out(db: Session, organisation_id: uuid.UUID, components: list[Component]) -> list[ComponentOut]:
    refs_by_id = get_external_references_bulk(db, organisation_id, "component", [c.id for c in components])
    type_ids = {c.component_type_id for c in components}
    types_by_id = {t.id: t for t in db.query(ComponentType).filter(ComponentType.id.in_(type_ids)).all()}
    return [
        ComponentOut(
            id=c.id,
            component_reference=c.component_reference,
            component_type_id=c.component_type_id,
            component_type_name=types_by_id[c.component_type_id].name if c.component_type_id in types_by_id else "Unknown",
            component_subtype=c.component_subtype,
            manufacturer=c.manufacturer,
            model=c.model,
            serial_number=refs_by_id.get(str(c.id), {}).get("MANUFACTURER_SERIAL_NUMBER"),
            installer=c.installer,
            installation_date=c.installation_date,
            commissioning_date=c.commissioning_date,
            warranty_start=c.warranty_start,
            warranty_expiry=c.warranty_expiry,
            expected_life_years=c.expected_life_years,
            indicative_replacement_date=c.indicative_replacement_date,
            status=c.status.value,
            development_id=c.development_id,
            building_id=c.building_id,
            property_id=c.property_id,
            space_id=c.space_id,
            parent_component_id=c.parent_component_id,
            source_type=c.source_type.value,
            source_dataset_id=c.source_dataset_id,
            original_reference=c.original_reference,
            created_at=c.created_at,
        )
        for c in components
    ]


def change_control_to_out(db: Session, organisation_id: uuid.UUID, change: ChangeControl) -> ChangeControlOut:
    refs = get_external_references(db, organisation_id, "change_control", change.id)
    return ChangeControlOut(
        id=change.id,
        change_reference=change.change_reference,
        specification_id=change.specification_id,
        related_entity_type=change.related_entity_type,
        related_entity_id=change.related_entity_id,
        previous_value=change.previous_value,
        proposed_value=change.proposed_value,
        reason=change.reason,
        impact_description=change.impact_description,
        status=change.status.value,
        approved_by=change.approved_by,
        approved_date=change.approved_date,
        implemented_specification_id=change.implemented_specification_id,
        external_approval_reference=refs.get("EXTERNAL_APPROVAL_REFERENCE"),
        source_type=change.source_type.value,
        created_by=change.created_by,
        created_at=change.created_at,
    )


def changes_to_out(db: Session, organisation_id: uuid.UUID, changes: list[ChangeControl]) -> list[ChangeControlOut]:
    refs_by_id = get_external_references_bulk(db, organisation_id, "change_control", [c.id for c in changes])
    return [
        ChangeControlOut(
            id=c.id,
            change_reference=c.change_reference,
            specification_id=c.specification_id,
            related_entity_type=c.related_entity_type,
            related_entity_id=c.related_entity_id,
            previous_value=c.previous_value,
            proposed_value=c.proposed_value,
            reason=c.reason,
            impact_description=c.impact_description,
            status=c.status.value,
            approved_by=c.approved_by,
            approved_date=c.approved_date,
            implemented_specification_id=c.implemented_specification_id,
            external_approval_reference=refs_by_id.get(str(c.id), {}).get("EXTERNAL_APPROVAL_REFERENCE"),
            source_type=c.source_type.value,
            created_by=c.created_by,
            created_at=c.created_at,
        )
        for c in changes
    ]


def warranty_to_out(warranty: Warranty) -> WarrantyOut:
    days_until_expiry = (warranty.expiry_date - date.today()).days
    return WarrantyOut(
        id=warranty.id,
        warranty_reference=warranty.warranty_reference,
        provider=warranty.provider,
        development_id=warranty.development_id,
        building_id=warranty.building_id,
        property_id=warranty.property_id,
        component_id=warranty.component_id,
        warranty_type=warranty.warranty_type,
        start_date=warranty.start_date,
        expiry_date=warranty.expiry_date,
        terms_reference=warranty.terms_reference,
        document_id=warranty.document_id,
        status=warranty.status.value,
        is_expired=days_until_expiry < 0,
        days_until_expiry=days_until_expiry,
        source_type=warranty.source_type.value,
        created_by=warranty.created_by,
        created_at=warranty.created_at,
    )


def warranties_to_out(warranties: list[Warranty]) -> list[WarrantyOut]:
    return [warranty_to_out(w) for w in warranties]
