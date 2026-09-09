"""Golden Thread composed view — architecture/03-development-domain.md
§4, spec §29. "Golden Thread is not a new table — it's a read-
composition across existing tables, expressed as one service function."
Nothing here writes anything; every field is read from tables that
already have their own create/write paths (Specification, Component,
Document, ExternalReference).

BUILDING -> DESIGN/SPECIFICATION -> COMPONENT -> RESPONSIBLE PARTY ->
EVIDENCE -> INSPECTION -> CHANGE -> APPROVAL/EXTERNAL REFERENCE ->
HANDOVER -> OPERATION. CHANGE is Sprint 10's own addition (`ChangeControl`
rows, matched by the same related_entity_type/related_entity_id every
other link here is matched by — not by specification_id, since the
Golden Thread traverses by *location*, and a location's change history
outlives any one specification revision). INSPECTION is Sprint 16's own
addition (`Inspection` rows against this building and each of its
components) — closing the gap this module's own NOT_YET_AVAILABLE list
used to name.

The per-component composition (specs/evidence/changes/responsible party/
external references/inspections) lives in app/development/composition.py
— Property 360 (Sprint 13) needed the exact same bundle, just gathered by
property instead of by building, so it was extracted there rather than
copied.
"""

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.development.composition import (
    build_component_view,
    changes_for,
    component_type_names_for,
    current_specifications,
    evidence_for,
    inspections_for,
)
from app.development.models import Building, Component, HandoverRecord, Property
from app.development.presenters import changes_to_out
from app.development.schemas import GoldenThreadOut, SpecificationOut
from app.documents.schemas import DocumentOut
from app.identifiers.service import get_external_references
from app.operations.compliance.schemas import InspectionOut

NOT_YET_AVAILABLE: list[str] = []


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
    component_type_names = component_type_names_for(db, components)
    component_views = [build_component_view(db, organisation_id, c, component_type_names) for c in components]

    handover_records = (
        db.query(HandoverRecord)
        .filter(HandoverRecord.organisation_id == organisation_id, HandoverRecord.property_id.in_(property_ids))
        .order_by(HandoverRecord.created_at.desc())
        .all()
        if property_ids
        else []
    )

    return GoldenThreadOut(
        building_id=building.id,
        building_reference=building.building_reference,
        building_name=building.name,
        specifications=[
            SpecificationOut.model_validate(s)
            for s in current_specifications(db, organisation_id, "building", building.id)
        ],
        evidence=[DocumentOut.model_validate(d) for d in evidence_for(db, organisation_id, "building", building.id)],
        changes=changes_to_out(db, organisation_id, changes_for(db, organisation_id, "building", building.id)),
        handover_records=handover_records,
        external_references=get_external_references(db, organisation_id, "building", building.id),
        inspections=[InspectionOut.model_validate(i) for i in inspections_for(db, organisation_id, "building", building.id)],
        components=component_views,
        not_yet_available=NOT_YET_AVAILABLE,
    )
