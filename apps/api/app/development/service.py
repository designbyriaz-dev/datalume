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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import (
    Building,
    Component,
    ComponentStatus,
    Development,
    Floor,
    Property,
    PropertyStatus,
    Space,
    Specification,
    SpecificationStatus,
)
from app.identifiers.models import ExternalReferenceType
from app.identifiers.service import generate_reference, record_external_reference
from app.platform.audit import record_audit_event


class HierarchyNotFoundError(ValueError):
    """A given development_id/building_id/floor_id doesn't exist in this
    organisation — the router maps this to a 404."""


class HierarchyMismatchError(ValueError):
    """Two given hierarchy ids are inconsistent (e.g. a floor_id whose
    building doesn't match the given building_id) — the router maps this
    to a 400."""


class UnsupportedEntityTypeError(ValueError):
    """A specification's related_entity_type isn't one of the five spec
    §27 names — the router maps this to a 400."""


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


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = (
        db.query(Property).filter(Property.id == property_id, Property.organisation_id == organisation_id).first()
    )
    if prop is None:
        raise HierarchyNotFoundError(f"Property {property_id} not found")
    return prop


def _get_org_space(db: Session, organisation_id: uuid.UUID, space_id: uuid.UUID) -> Space:
    space = db.query(Space).filter(Space.id == space_id, Space.organisation_id == organisation_id).first()
    if space is None:
        raise HierarchyNotFoundError(f"Space {space_id} not found")
    return space


def _get_org_component(db: Session, organisation_id: uuid.UUID, component_id: uuid.UUID) -> Component:
    component = (
        db.query(Component)
        .filter(Component.id == component_id, Component.organisation_id == organisation_id)
        .first()
    )
    if component is None:
        raise HierarchyNotFoundError(f"Component {component_id} not found")
    return component


SPECIFICATION_ENTITY_TYPES = ("development", "building", "property", "space", "component")


def _validate_related_entity(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> None:
    # Existence/ownership check only, same as create_component's
    # attachment points — a specification doesn't need the entity in any
    # particular state, just that it's real and belongs to this org.
    if entity_type == "development":
        _get_org_development(db, organisation_id, entity_id)
    elif entity_type == "building":
        _get_org_building(db, organisation_id, entity_id)
    elif entity_type == "property":
        _get_org_property(db, organisation_id, entity_id)
    elif entity_type == "space":
        _get_org_space(db, organisation_id, entity_id)
    elif entity_type == "component":
        _get_org_component(db, organisation_id, entity_id)
    else:
        raise UnsupportedEntityTypeError(
            f"related_entity_type must be one of {SPECIFICATION_ENTITY_TYPES}, got {entity_type!r}"
        )


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


def _record_optional_external_references(
    db: Session,
    organisation_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    values: dict[ExternalReferenceType, str | None],
    *,
    source_type: SourceType,
    source_dataset_id: uuid.UUID | None,
    import_job_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """create_development/create_building/create_property all take a
    handful of optional external-identifier kwargs for ergonomics (the
    caller still just passes uprn="..." etc.) but store them as
    ExternalReference rows, never columns — see identifiers/models.py."""
    for reference_type, value in values.items():
        if value:
            record_external_reference(
                db,
                organisation_id,
                entity_type=entity_type,
                entity_id=entity_id,
                reference_type=reference_type,
                value=value,
                source_type=source_type,
                source_dataset_id=source_dataset_id,
                import_job_id=import_job_id,
                actor_user_id=actor_user_id,
            )


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
        development_reference=generate_reference(db, organisation_id, "DEVELOPMENT"),
        name=name,
        description=description,
        address=address,
        postcode=postcode,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(dev)
    db.flush()

    _record_optional_external_references(
        db,
        organisation_id,
        "development",
        dev.id,
        {
            ExternalReferenceType.PLANNING_REFERENCE: planning_reference,
            ExternalReferenceType.BUILDING_CONTROL_REFERENCE: building_control_reference,
            ExternalReferenceType.BSR_REFERENCE: bsr_reference,
        },
        source_type=source_type,
        source_dataset_id=None,
        import_job_id=None,
        actor_user_id=actor_user_id,
    )

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
        building_reference=generate_reference(db, organisation_id, "BUILDING"),
        name=name,
        building_type=building_type,
        address=address,
        storeys=storeys,
        source_type=source_type,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(building)
    db.flush()

    _record_optional_external_references(
        db,
        organisation_id,
        "building",
        building.id,
        {
            ExternalReferenceType.BUILDING_CONTROL_REFERENCE: building_control_reference,
            ExternalReferenceType.BSR_REFERENCE: bsr_reference,
        },
        source_type=source_type,
        source_dataset_id=None,
        import_job_id=None,
        actor_user_id=actor_user_id,
    )

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
        property_reference=generate_reference(db, organisation_id, "PROPERTY"),
        address=address,
        postcode=postcode,
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

    _record_optional_external_references(
        db,
        organisation_id,
        "property",
        prop.id,
        {ExternalReferenceType.UPRN: uprn},
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        actor_user_id=actor_user_id,
    )

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


def _indicative_replacement_date(installation_date: date | None, expected_life_years: int | None) -> date | None:
    if installation_date is None or expected_life_years is None:
        return None
    return installation_date + timedelta(days=round(expected_life_years * 365.25))


def create_component(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    component_type_id: uuid.UUID,
    component_subtype: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    serial_number: str | None = None,
    installer: str | None = None,
    installation_date: date | None = None,
    commissioning_date: date | None = None,
    warranty_start: date | None = None,
    warranty_expiry: date | None = None,
    expected_life_years: int | None = None,
    status: ComponentStatus = ComponentStatus.ACTIVE,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    space_id: uuid.UUID | None = None,
    parent_component_id: uuid.UUID | None = None,
    source_type: SourceType,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Component:
    # Existence/ownership checks only — unlike Property, a component's
    # attachment points aren't cross-validated against each other (spec
    # §24: a component can belong to a building with no specific property,
    # a property with no specific space, etc. — there's no single strict
    # tree position to derive here the way floor->building->development
    # works for Property).
    if development_id is not None:
        _get_org_development(db, organisation_id, development_id)
    if building_id is not None:
        _get_org_building(db, organisation_id, building_id)
    if property_id is not None:
        _get_org_property(db, organisation_id, property_id)
    if space_id is not None:
        _get_org_space(db, organisation_id, space_id)
    if parent_component_id is not None:
        _get_org_component(db, organisation_id, parent_component_id)

    component = Component(
        organisation_id=organisation_id,
        development_id=development_id,
        building_id=building_id,
        property_id=property_id,
        space_id=space_id,
        parent_component_id=parent_component_id,
        component_reference=generate_reference(db, organisation_id, "COMPONENT"),
        component_type_id=component_type_id,
        component_subtype=component_subtype,
        manufacturer=manufacturer,
        model=model,
        installer=installer,
        installation_date=installation_date,
        commissioning_date=commissioning_date,
        warranty_start=warranty_start,
        warranty_expiry=warranty_expiry,
        expected_life_years=expected_life_years,
        indicative_replacement_date=_indicative_replacement_date(installation_date, expected_life_years),
        status=status,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(component)
    db.flush()

    _record_optional_external_references(
        db,
        organisation_id,
        "component",
        component.id,
        {ExternalReferenceType.MANUFACTURER_SERIAL_NUMBER: serial_number},
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        actor_user_id=actor_user_id,
    )

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="component.created",
        entity_type="component",
        entity_id=str(component.id),
        after={"component_reference": component.component_reference, "component_type_id": str(component_type_id)},
    )
    return component


def _get_org_specification(db: Session, organisation_id: uuid.UUID, specification_id: uuid.UUID) -> Specification:
    spec = (
        db.query(Specification)
        .filter(Specification.id == specification_id, Specification.organisation_id == organisation_id)
        .first()
    )
    if spec is None:
        raise HierarchyNotFoundError(f"Specification {specification_id} not found")
    return spec


def create_specification(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    related_entity_type: str,
    related_entity_id: uuid.UUID,
    title: str,
    description: str | None = None,
    related_component_type: str | None = None,
    effective_date: date | None = None,
    source_document_id: uuid.UUID | None = None,
    source_type: SourceType = SourceType.MANUAL,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Specification:
    _validate_related_entity(db, organisation_id, related_entity_type, related_entity_id)
    if source_document_id is not None:
        # Existence/ownership only — Document itself is untouched by this
        # link (spec §27's source_document is metadata, not a new file).
        from app.documents.models import Document

        exists = (
            db.query(Document.id)
            .filter(Document.id == source_document_id, Document.organisation_id == organisation_id)
            .first()
        )
        if exists is None:
            raise HierarchyNotFoundError(f"Document {source_document_id} not found")

    spec_id = uuid.uuid4()
    spec = Specification(
        id=spec_id,
        lineage_id=spec_id,
        organisation_id=organisation_id,
        specification_reference=generate_reference(db, organisation_id, "SPECIFICATION"),
        related_entity_type=related_entity_type,
        related_entity_id=str(related_entity_id),
        title=title,
        description=description,
        revision="A",
        status=SpecificationStatus.ACTIVE,
        effective_date=effective_date,
        related_component_type=related_component_type,
        source_document_id=source_document_id,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(spec)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="specification.created",
        entity_type="specification",
        entity_id=str(spec.id),
        after={
            "specification_reference": spec.specification_reference,
            "related_entity_type": related_entity_type,
            "related_entity_id": str(related_entity_id),
        },
    )
    return spec


def create_specification_revision(
    db: Session,
    organisation_id: uuid.UUID,
    previous: Specification,
    *,
    revision: str,
    title: str | None = None,
    description: str | None = None,
    related_component_type: str | None = None,
    effective_date: date | None = None,
    source_document_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Specification:
    """"A change must NOT simply overwrite the previous specification"
    (spec §26) — a new row, the old one marked SUPERSEDED, same append-
    only pattern as Document's upload_new_version."""
    if previous.status == SpecificationStatus.SUPERSEDED:
        raise HierarchyMismatchError(
            "This is not the current revision — create a new revision from the latest one instead"
        )

    new_id = uuid.uuid4()
    new_version = Specification(
        id=new_id,
        lineage_id=previous.lineage_id,
        organisation_id=organisation_id,
        specification_reference=previous.specification_reference,
        related_entity_type=previous.related_entity_type,
        related_entity_id=previous.related_entity_id,
        title=title if title is not None else previous.title,
        description=description if description is not None else previous.description,
        revision=revision,
        status=SpecificationStatus.ACTIVE,
        effective_date=effective_date,
        related_component_type=(
            related_component_type if related_component_type is not None else previous.related_component_type
        ),
        source_document_id=source_document_id if source_document_id is not None else previous.source_document_id,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(new_version)
    db.flush()

    previous.status = SpecificationStatus.SUPERSEDED
    previous.superseded_date = effective_date or date.today()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="specification.new_revision",
        entity_type="specification",
        entity_id=str(new_version.id),
        before={"superseded_specification_id": str(previous.id)},
        after={"revision": revision},
    )
    return new_version


def approve_specification(
    db: Session, organisation_id: uuid.UUID, specification: Specification, *, actor_user_id: uuid.UUID
) -> Specification:
    specification.approved_by = actor_user_id
    specification.approved_at = datetime.now(timezone.utc)

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="specification.approved",
        entity_type="specification",
        entity_id=str(specification.id),
        after={"approved_by": str(actor_user_id)},
    )
    return specification
