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
    ChangeControl,
    ChangeControlStatus,
    Component,
    ComponentStatus,
    Defect,
    DefectSeverity,
    DefectStatus,
    Development,
    Floor,
    HandoverReadinessCheckWeight,
    HandoverRecord,
    PlannedInvestmentConfig,
    PlannedInvestmentWeight,
    Property,
    PropertyStatus,
    Space,
    Specification,
    SpecificationStatus,
    Warranty,
    WarrantyStatus,
)
from app.identifiers.models import ExternalReferenceType
from app.identifiers.service import generate_reference, get_external_references, record_external_reference
from app.platform.audit import record_audit_event


class HandoverNotReadyError(ValueError):
    """The development's handover readiness score is below the required
    threshold and no override_reason was supplied — the router maps this
    to a 400."""


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


class InvalidDefectTransitionError(ValueError):
    """The requested status transition isn't allowed from a defect's
    current status — the router maps this to a 400."""


class InvalidChangeControlTransitionError(ValueError):
    """The requested status transition isn't allowed from a change
    control's current status — the router maps this to a 400."""


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
    number_of_planned_properties: int | None = None,
    planning_reference: str | None = None,
    building_control_reference: str | None = None,
    bsr_reference: str | None = None,
    source_type: SourceType = SourceType.MANUAL,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Development:
    dev = Development(
        organisation_id=organisation_id,
        development_reference=generate_reference(db, organisation_id, "DEVELOPMENT"),
        name=name,
        description=description,
        address=address,
        postcode=postcode,
        number_of_planned_properties=number_of_planned_properties,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
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
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
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
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
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
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
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
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
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


SPECIFICATION_SNAPSHOT_FIELDS = ("title", "description", "related_component_type", "effective_date")


def _specification_snapshot(specification: Specification) -> dict:
    snapshot = {field: getattr(specification, field) for field in SPECIFICATION_SNAPSHOT_FIELDS}
    if snapshot["effective_date"] is not None:
        snapshot["effective_date"] = snapshot["effective_date"].isoformat()
    return snapshot


def _get_org_change_control(db: Session, organisation_id: uuid.UUID, change_control_id: uuid.UUID) -> ChangeControl:
    change = (
        db.query(ChangeControl)
        .filter(ChangeControl.id == change_control_id, ChangeControl.organisation_id == organisation_id)
        .first()
    )
    if change is None:
        raise HierarchyNotFoundError(f"Change control {change_control_id} not found")
    return change


def _require_change_control_transition(
    change: ChangeControl, allowed_from: tuple[ChangeControlStatus, ...], action: str
) -> None:
    if change.status not in allowed_from:
        raise InvalidChangeControlTransitionError(
            f"Cannot {action} a change control in status {change.status.value}"
        )


def submit_change_control(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    specification_id: uuid.UUID,
    proposed_value: dict,
    reason: str,
    impact_description: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ChangeControl:
    """previous_value is always captured HERE, from the specification's
    own current fields — never accepted from the caller — so it stays an
    accurate record of what was actually being proposed against,
    independent of anything that happens to the specification later
    (architecture/03-development-domain.md §7)."""
    specification = _get_org_specification(db, organisation_id, specification_id)
    if specification.status == SpecificationStatus.SUPERSEDED:
        raise HierarchyMismatchError("Cannot propose a change against a superseded specification revision")

    change = ChangeControl(
        organisation_id=organisation_id,
        change_reference=generate_reference(db, organisation_id, "CHANGE_CONTROL"),
        specification_id=specification.id,
        related_entity_type=specification.related_entity_type,
        related_entity_id=specification.related_entity_id,
        previous_value=_specification_snapshot(specification),
        proposed_value=proposed_value,
        reason=reason,
        impact_description=impact_description,
        status=ChangeControlStatus.PROPOSED,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(change)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.submitted",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"change_reference": change.change_reference, "specification_id": str(specification.id)},
    )
    return change


def start_change_control_review(
    db: Session, organisation_id: uuid.UUID, change: ChangeControl, *, actor_user_id: uuid.UUID | None = None
) -> ChangeControl:
    _require_change_control_transition(change, (ChangeControlStatus.PROPOSED,), "start review on")
    change.status = ChangeControlStatus.UNDER_REVIEW
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.under_review",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"status": change.status.value},
    )
    return change


def approve_change_control(
    db: Session,
    organisation_id: uuid.UUID,
    change: ChangeControl,
    *,
    external_approval_reference: str | None = None,
    actor_user_id: uuid.UUID,
) -> ChangeControl:
    _require_change_control_transition(
        change, (ChangeControlStatus.PROPOSED, ChangeControlStatus.UNDER_REVIEW), "approve"
    )
    change.status = ChangeControlStatus.APPROVED
    change.approved_by = actor_user_id
    change.approved_date = date.today()

    if external_approval_reference:
        record_external_reference(
            db,
            organisation_id,
            entity_type="change_control",
            entity_id=change.id,
            reference_type=ExternalReferenceType.EXTERNAL_APPROVAL_REFERENCE,
            value=external_approval_reference,
            source_type=SourceType.MANUAL,
            actor_user_id=actor_user_id,
        )

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.approved",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"approved_by": str(actor_user_id)},
    )
    return change


def reject_change_control(
    db: Session, organisation_id: uuid.UUID, change: ChangeControl, *, actor_user_id: uuid.UUID | None = None
) -> ChangeControl:
    _require_change_control_transition(
        change, (ChangeControlStatus.PROPOSED, ChangeControlStatus.UNDER_REVIEW), "reject"
    )
    change.status = ChangeControlStatus.REJECTED
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.rejected",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"status": change.status.value},
    )
    return change


def cancel_change_control(
    db: Session, organisation_id: uuid.UUID, change: ChangeControl, *, actor_user_id: uuid.UUID | None = None
) -> ChangeControl:
    _require_change_control_transition(
        change,
        (ChangeControlStatus.PROPOSED, ChangeControlStatus.UNDER_REVIEW, ChangeControlStatus.APPROVED),
        "cancel",
    )
    change.status = ChangeControlStatus.CANCELLED
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.cancelled",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"status": change.status.value},
    )
    return change


def _next_revision_label(specification: Specification) -> str:
    # Single uppercase letter is the common case (Sprint 9's own UI only
    # ever produces "A", "B", "C", ...) — increment it. Anything else
    # (a custom revision label supplied through the API directly) falls
    # back to a numbered label rather than guessing at a letter sequence
    # that was never being followed in the first place.
    current = specification.revision
    if len(current) == 1 and "A" <= current <= "Y":
        return chr(ord(current) + 1)
    return f"{current}.1"


def implement_change_control(
    db: Session, organisation_id: uuid.UUID, change: ChangeControl, *, actor_user_id: uuid.UUID | None = None
) -> ChangeControl:
    """The one action that actually touches Specification: creates the
    new revision via create_specification_revision (Sprint 9's own
    append-only path — the prior row is marked SUPERSEDED, never edited
    in place) using proposed_value, and records which new row resulted."""
    _require_change_control_transition(change, (ChangeControlStatus.APPROVED,), "implement")

    specification = _get_org_specification(db, organisation_id, change.specification_id)
    if specification.status == SpecificationStatus.SUPERSEDED:
        raise HierarchyMismatchError(
            "The target specification has already been superseded — this change can no longer be implemented as-is"
        )

    new_version = create_specification_revision(
        db,
        organisation_id,
        specification,
        revision=_next_revision_label(specification),
        title=change.proposed_value.get("title"),
        description=change.proposed_value.get("description"),
        related_component_type=change.proposed_value.get("related_component_type"),
        effective_date=(
            date.fromisoformat(change.proposed_value["effective_date"])
            if change.proposed_value.get("effective_date")
            else None
        ),
        actor_user_id=actor_user_id,
    )

    change.status = ChangeControlStatus.IMPLEMENTED
    change.implemented_specification_id = new_version.id

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="change_control.implemented",
        entity_type="change_control",
        entity_id=str(change.id),
        after={"implemented_specification_id": str(new_version.id)},
    )
    return change


def get_change_control_external_approval_reference(
    db: Session, organisation_id: uuid.UUID, change: ChangeControl
) -> str | None:
    return get_external_references(db, organisation_id, "change_control", change.id).get(
        ExternalReferenceType.EXTERNAL_APPROVAL_REFERENCE.value
    )


DEFECT_TRANSITIONS: dict[DefectStatus, tuple[DefectStatus, ...]] = {
    DefectStatus.OPEN: (DefectStatus.ASSIGNED, DefectStatus.REJECTED),
    DefectStatus.ASSIGNED: (DefectStatus.IN_PROGRESS, DefectStatus.REJECTED),
    DefectStatus.IN_PROGRESS: (DefectStatus.READY_FOR_INSPECTION, DefectStatus.REJECTED),
    # A failed inspection sends work back to IN_PROGRESS rather than
    # forcing a new defect to be raised for the same snag.
    DefectStatus.READY_FOR_INSPECTION: (DefectStatus.COMPLETED, DefectStatus.IN_PROGRESS),
    DefectStatus.COMPLETED: (DefectStatus.CLOSED,),
    DefectStatus.REJECTED: (DefectStatus.CLOSED,),
    DefectStatus.CLOSED: (),
}


def _get_org_defect(db: Session, organisation_id: uuid.UUID, defect_id: uuid.UUID) -> Defect:
    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.organisation_id == organisation_id).first()
    if defect is None:
        raise HierarchyNotFoundError(f"Defect {defect_id} not found")
    return defect


def create_defect(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    category: str,
    description: str,
    reported_date: date,
    severity: str = "MEDIUM",
    contractor: str | None = None,
    responsible_party: str | None = None,
    target_date: date | None = None,
    estimated_cost_pence: int | None = None,
    warranty_related: bool = False,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    source_type: SourceType = SourceType.MANUAL,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Defect:
    # Existence/ownership checks only, independent and non-cross-
    # validated — same reasoning as create_component's attachment
    # points (spec §24).
    if development_id is not None:
        _get_org_development(db, organisation_id, development_id)
    if building_id is not None:
        _get_org_building(db, organisation_id, building_id)
    if property_id is not None:
        _get_org_property(db, organisation_id, property_id)
    if component_id is not None:
        _get_org_component(db, organisation_id, component_id)

    defect = Defect(
        organisation_id=organisation_id,
        defect_reference=generate_reference(db, organisation_id, "DEFECT"),
        development_id=development_id,
        building_id=building_id,
        property_id=property_id,
        component_id=component_id,
        category=category,
        description=description,
        severity=DefectSeverity(severity),
        reported_date=reported_date,
        contractor=contractor,
        responsible_party=responsible_party,
        target_date=target_date,
        status=DefectStatus.OPEN,
        estimated_cost_pence=estimated_cost_pence,
        warranty_related=warranty_related,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(defect)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="defect.reported",
        entity_type="defect",
        entity_id=str(defect.id),
        after={"defect_reference": defect.defect_reference, "category": category, "severity": severity},
    )
    return defect


def update_defect_status(
    db: Session,
    organisation_id: uuid.UUID,
    defect: Defect,
    *,
    new_status: str,
    completion_date: date | None = None,
    actual_cost_pence: int | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Defect:
    target = DefectStatus(new_status)
    allowed = DEFECT_TRANSITIONS.get(defect.status, ())
    if target not in allowed:
        raise InvalidDefectTransitionError(f"Cannot move a defect from {defect.status.value} to {target.value}")

    previous_status = defect.status
    defect.status = target
    if target == DefectStatus.COMPLETED:
        defect.completion_date = completion_date or date.today()
    if actual_cost_pence is not None:
        defect.actual_cost_pence = actual_cost_pence

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="defect.status_changed",
        entity_type="defect",
        entity_id=str(defect.id),
        before={"status": previous_status.value},
        after={"status": target.value},
    )
    return defect


def _get_org_warranty(db: Session, organisation_id: uuid.UUID, warranty_id: uuid.UUID) -> Warranty:
    warranty = (
        db.query(Warranty).filter(Warranty.id == warranty_id, Warranty.organisation_id == organisation_id).first()
    )
    if warranty is None:
        raise HierarchyNotFoundError(f"Warranty {warranty_id} not found")
    return warranty


def create_warranty(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    provider: str,
    warranty_type: str,
    start_date: date,
    expiry_date: date,
    terms_reference: str | None = None,
    document_id: uuid.UUID | None = None,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    source_type: SourceType = SourceType.MANUAL,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Warranty:
    if development_id is not None:
        _get_org_development(db, organisation_id, development_id)
    if building_id is not None:
        _get_org_building(db, organisation_id, building_id)
    if property_id is not None:
        _get_org_property(db, organisation_id, property_id)
    if component_id is not None:
        _get_org_component(db, organisation_id, component_id)
    if document_id is not None:
        from app.documents.models import Document

        exists = (
            db.query(Document.id)
            .filter(Document.id == document_id, Document.organisation_id == organisation_id)
            .first()
        )
        if exists is None:
            raise HierarchyNotFoundError(f"Document {document_id} not found")

    if expiry_date <= start_date:
        raise HierarchyMismatchError("A warranty's expiry_date must be after its start_date")

    warranty = Warranty(
        organisation_id=organisation_id,
        warranty_reference=generate_reference(db, organisation_id, "WARRANTY"),
        provider=provider,
        development_id=development_id,
        building_id=building_id,
        property_id=property_id,
        component_id=component_id,
        warranty_type=warranty_type,
        start_date=start_date,
        expiry_date=expiry_date,
        terms_reference=terms_reference,
        document_id=document_id,
        status=WarrantyStatus.ACTIVE,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(warranty)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="warranty.created",
        entity_type="warranty",
        entity_id=str(warranty.id),
        after={"warranty_reference": warranty.warranty_reference, "provider": provider, "expiry_date": str(expiry_date)},
    )
    return warranty


def void_warranty(
    db: Session, organisation_id: uuid.UUID, warranty: Warranty, *, actor_user_id: uuid.UUID | None = None
) -> Warranty:
    warranty.status = WarrantyStatus.VOID
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="warranty.voided",
        entity_type="warranty",
        entity_id=str(warranty.id),
        after={"status": "VOID"},
    )
    return warranty


def get_or_create_handover_readiness_weight(
    db: Session, organisation_id: uuid.UUID, check_code: str, default_weight: float
) -> HandoverReadinessCheckWeight:
    weight = (
        db.query(HandoverReadinessCheckWeight)
        .filter(
            HandoverReadinessCheckWeight.organisation_id == organisation_id,
            HandoverReadinessCheckWeight.check_code == check_code,
        )
        .with_for_update()
        .first()
    )
    if weight is not None:
        return weight
    weight = HandoverReadinessCheckWeight(organisation_id=organisation_id, check_code=check_code, weight=default_weight)
    db.add(weight)
    db.flush()
    return weight


def list_handover_readiness_weights(db: Session, organisation_id: uuid.UUID) -> list[HandoverReadinessCheckWeight]:
    from app.development.handover import DEFAULT_CHECK_WEIGHTS

    for code, default in DEFAULT_CHECK_WEIGHTS.items():
        get_or_create_handover_readiness_weight(db, organisation_id, code, default)
    return (
        db.query(HandoverReadinessCheckWeight)
        .filter(HandoverReadinessCheckWeight.organisation_id == organisation_id)
        .all()
    )


def set_handover_readiness_weight(
    db: Session, organisation_id: uuid.UUID, check_code: str, weight: float
) -> HandoverReadinessCheckWeight:
    from app.development.handover import DEFAULT_CHECK_WEIGHTS

    if check_code not in DEFAULT_CHECK_WEIGHTS:
        raise HierarchyNotFoundError(f"Unknown handover readiness check_code: {check_code}")
    row = get_or_create_handover_readiness_weight(db, organisation_id, check_code, DEFAULT_CHECK_WEIGHTS[check_code])
    row.weight = weight
    db.flush()
    return row


def get_or_create_planned_investment_weight(
    db: Session, organisation_id: uuid.UUID, factor_code: str, default_weight: float
) -> PlannedInvestmentWeight:
    weight = (
        db.query(PlannedInvestmentWeight)
        .filter(
            PlannedInvestmentWeight.organisation_id == organisation_id,
            PlannedInvestmentWeight.factor_code == factor_code,
        )
        .with_for_update()
        .first()
    )
    if weight is not None:
        return weight
    weight = PlannedInvestmentWeight(organisation_id=organisation_id, factor_code=factor_code, weight=default_weight)
    db.add(weight)
    db.flush()
    return weight


def list_planned_investment_weights(db: Session, organisation_id: uuid.UUID) -> list[PlannedInvestmentWeight]:
    from app.development.planned_investment import DEFAULT_FACTOR_WEIGHTS

    for code, default in DEFAULT_FACTOR_WEIGHTS.items():
        get_or_create_planned_investment_weight(db, organisation_id, code, default)
    return db.query(PlannedInvestmentWeight).filter(PlannedInvestmentWeight.organisation_id == organisation_id).all()


def set_planned_investment_weight(
    db: Session, organisation_id: uuid.UUID, factor_code: str, weight: float
) -> PlannedInvestmentWeight:
    from app.development.planned_investment import DEFAULT_FACTOR_WEIGHTS

    if factor_code not in DEFAULT_FACTOR_WEIGHTS:
        raise HierarchyNotFoundError(f"Unknown planned investment factor_code: {factor_code}")
    row = get_or_create_planned_investment_weight(db, organisation_id, factor_code, DEFAULT_FACTOR_WEIGHTS[factor_code])
    row.weight = weight
    db.flush()
    return row


def get_or_create_planned_investment_config(db: Session, organisation_id: uuid.UUID) -> PlannedInvestmentConfig:
    config = (
        db.query(PlannedInvestmentConfig)
        .filter(PlannedInvestmentConfig.organisation_id == organisation_id)
        .with_for_update()
        .first()
    )
    if config is not None:
        return config
    config = PlannedInvestmentConfig(organisation_id=organisation_id)
    db.add(config)
    db.flush()
    return config


def set_planned_investment_config(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    repair_frequency_window_months: int | None,
    repair_frequency_threshold: int | None,
) -> PlannedInvestmentConfig:
    config = get_or_create_planned_investment_config(db, organisation_id)
    if repair_frequency_window_months is not None:
        config.repair_frequency_window_months = repair_frequency_window_months
    if repair_frequency_threshold is not None:
        config.repair_frequency_threshold = repair_frequency_threshold
    db.flush()
    return config


HANDOVER_READINESS_THRESHOLD_PCT = 100.0
# v1 requires full readiness (or an explicit permitted override) rather
# than a second per-org configurable threshold — spec §37 only calls out
# the *scoring methodology* (the checks and their weights) as needing to
# be transparent/configurable, not the pass/fail bar itself, and
# HANDOVER_MANAGER+'s override path (architecture §9 step 1) already
# covers the real-world case where a development ships below 100% for a
# documented reason.


def authorise_handover(
    db: Session,
    organisation_id: uuid.UUID,
    development: Development,
    *,
    override_reason: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[HandoverRecord]:
    """architecture/03-development-domain.md §9.
    HandoverService.authorise: assert readiness (or a permitted
    override), flip every in-scope READY_FOR_HANDOVER property to
    HANDED_OVER, write one HandoverRecord per property, audit each.
    Properties not currently READY_FOR_HANDOVER are left untouched —
    handover can be authorised in phases as blocks of a development
    reach readiness at different times."""
    from app.development.handover import compute_handover_readiness, properties_in_development

    score_pct, checks = compute_handover_readiness(db, organisation_id, development.id)
    if score_pct < HANDOVER_READINESS_THRESHOLD_PCT and not override_reason:
        raise HandoverNotReadyError(
            f"Handover readiness is {score_pct}%, below the required {HANDOVER_READINESS_THRESHOLD_PCT}% "
            "— supply an override_reason to authorise anyway"
        )

    snapshot = [
        {
            "check_code": c.check_code,
            "label": c.label,
            "weight": c.weight,
            "pass_ratio": round(c.pass_ratio, 3),
            "missing_items": c.missing_items,
        }
        for c in checks
    ]

    properties = [
        p for p in properties_in_development(db, organisation_id, development.id) if p.status == PropertyStatus.READY_FOR_HANDOVER
    ]

    records: list[HandoverRecord] = []
    for prop in properties:
        prop.status = PropertyStatus.HANDED_OVER
        record = HandoverRecord(
            organisation_id=organisation_id,
            property_id=prop.id,
            development_id=development.id,
            readiness_score_pct=score_pct,
            readiness_snapshot=snapshot,
            override_reason=override_reason,
            source_type=SourceType.MANUAL,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(record)
        records.append(record)

        record_audit_event(
            db,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action_code="property.handed_over",
            entity_type="property",
            entity_id=str(prop.id),
            before={"status": "READY_FOR_HANDOVER"},
            after={"status": "HANDED_OVER", "readiness_score_pct": score_pct},
        )

    db.flush()
    return records


def update_property_status(
    db: Session, organisation_id: uuid.UUID, prop: Property, *, new_status: str, actor_user_id: uuid.UUID | None = None
) -> Property:
    target = PropertyStatus(new_status)
    if target == PropertyStatus.HANDED_OVER:
        raise HierarchyMismatchError(
            "HANDED_OVER can only be set by authorising handover, not by a direct status update"
        )
    previous = prop.status
    prop.status = target
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="property.status_changed",
        entity_type="property",
        entity_id=str(prop.id),
        before={"status": previous.value},
        after={"status": target.value},
    )
    return prop
