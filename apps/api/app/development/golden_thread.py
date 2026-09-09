"""Golden Thread composed view — architecture/03-development-domain.md
§4, spec §29. "Golden Thread is not a new table — it's a read-
composition across existing tables, expressed as one service function."
Nothing here writes anything; every field is read from tables that
already have their own create/write paths (Specification, Component,
Document, ExternalReference).

BUILDING -> DESIGN/SPECIFICATION -> COMPONENT -> RESPONSIBLE PARTY ->
EVIDENCE -> INSPECTION -> CHANGE -> APPROVAL/EXTERNAL REFERENCE ->
HANDOVER -> OPERATION. Inspection, change control and handover have no
canonical table yet (Sprints 16, 10, 12) — see GoldenThreadOut's
not_yet_available list, which is the honest, explicit stand-in rather
than silently omitting those links.
"""

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.models import User
from app.development.models import Building, Component, ComponentType, Property, Specification, SpecificationStatus
from app.development.schemas import (
    GoldenThreadComponentOut,
    GoldenThreadOut,
    GoldenThreadResponsiblePartyOut,
    SpecificationOut,
)
from app.documents.models import Document
from app.documents.schemas import DocumentOut
from app.identifiers.service import get_external_references

NOT_YET_AVAILABLE = ["inspections (Sprint 16)", "change_control (Sprint 10)", "handover_records (Sprint 12)"]


def _current_specifications(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list:
    return (
        db.query(Specification)
        .filter(
            Specification.organisation_id == organisation_id,
            Specification.related_entity_type == entity_type,
            Specification.related_entity_id == str(entity_id),
            Specification.status != SpecificationStatus.SUPERSEDED,
        )
        .order_by(Specification.created_at.desc())
        .all()
    )


def _evidence(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list:
    return (
        db.query(Document)
        .filter(
            Document.organisation_id == organisation_id,
            Document.related_entity_type == entity_type,
            Document.related_entity_id == str(entity_id),
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def _responsible_party(
    db: Session, organisation_id: uuid.UUID, component: Component, external_references: dict[str, str]
) -> GoldenThreadResponsiblePartyOut:
    creator = db.query(User).filter(User.id == component.created_by).first() if component.created_by else None
    return GoldenThreadResponsiblePartyOut(
        created_by_name=creator.name if creator else None,
        created_by_email=creator.email if creator else None,
        source_type=component.source_type.value,
        source_system=component.source_system,
        contractor_reference=external_references.get("CONTRACTOR_REFERENCE"),
    )


def get_golden_thread(db: Session, organisation_id: uuid.UUID, building: Building) -> GoldenThreadOut:
    property_ids = [
        row[0]
        for row in db.query(Property.id).filter(
            Property.building_id == building.id, Property.organisation_id == organisation_id
        )
    ]
    attachment_condition = (
        or_(Component.building_id == building.id, Component.property_id.in_(property_ids))
        if property_ids
        else Component.building_id == building.id
    )
    components = (
        db.query(Component)
        .filter(Component.organisation_id == organisation_id, attachment_condition)
        .order_by(Component.created_at)
        .all()
    )
    component_type_names: dict[uuid.UUID, str] = {}
    if components:
        type_ids = [c.component_type_id for c in components]
        component_type_names = {
            ct.id: ct.name for ct in db.query(ComponentType).filter(ComponentType.id.in_(type_ids))
        }

    component_views = []
    for component in components:
        external_references = get_external_references(db, organisation_id, "component", component.id)
        component_views.append(
            GoldenThreadComponentOut(
                id=component.id,
                component_reference=component.component_reference,
                component_type_name=component_type_names.get(component.component_type_id, "Unknown"),
                status=component.status.value,
                specifications=[
                    SpecificationOut.model_validate(s)
                    for s in _current_specifications(db, organisation_id, "component", component.id)
                ],
                responsible_party=_responsible_party(db, organisation_id, component, external_references),
                evidence=[DocumentOut.model_validate(d) for d in _evidence(db, organisation_id, "component", component.id)],
                external_references=external_references,
            )
        )

    return GoldenThreadOut(
        building_id=building.id,
        building_reference=building.building_reference,
        building_name=building.name,
        specifications=[
            SpecificationOut.model_validate(s)
            for s in _current_specifications(db, organisation_id, "building", building.id)
        ],
        evidence=[DocumentOut.model_validate(d) for d in _evidence(db, organisation_id, "building", building.id)],
        external_references=get_external_references(db, organisation_id, "building", building.id),
        components=component_views,
        not_yet_available=NOT_YET_AVAILABLE,
    )
