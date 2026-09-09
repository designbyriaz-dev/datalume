"""Shared create-entity service functions — architecture/02-data-platform.md
§3: "manual entry and file import produce identical, equally valid
records" because both call the same function here. app/development/router.py
(manual "+Add Property") and app/development/importers.py (the ingestion
IMPORTERS["PROPERTIES"] registration) are both thin callers of
create_property — neither duplicates the other's logic.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Property, PropertyStatus, Space
from app.development.reference import next_property_reference
from app.platform.audit import record_audit_event


def create_property(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    address: str,
    postcode: str | None = None,
    uprn: str | None = None,
    property_type: str | None = None,
    status: PropertyStatus = PropertyStatus.OPERATIONAL,
    source_type: SourceType,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Property:
    prop = Property(
        organisation_id=organisation_id,
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
    property_id: uuid.UUID,
    *,
    name: str,
    space_type: str | None = None,
    source_type: SourceType = SourceType.MANUAL,
    actor_user_id: uuid.UUID | None = None,
) -> Space:
    space = Space(
        organisation_id=organisation_id,
        property_id=property_id,
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
        after={"name": name, "property_id": str(property_id)},
    )
    return space
