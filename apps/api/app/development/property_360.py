"""Property 360 — architecture/03-development-domain.md (all sections),
spec §41. A read-composition exactly like Golden Thread (§4) and
Handover Readiness (§8), just scoped to one property instead of one
building or development. See Property360Out's docstring for what's
covered and what's honestly listed as not yet available.
"""

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.models import User
from app.data_health.rules import run_data_health_checks
from app.data_health.schemas import FindingOut
from app.development.composition import build_component_view, changes_for, component_type_names_for, current_specifications, evidence_for
from app.development.models import (
    Building,
    Component,
    Defect,
    Development,
    Floor,
    HandoverRecord,
    Property,
    Space,
    Warranty,
)
from app.development.presenters import building_to_out, changes_to_out, development_to_out, property_to_out, warranties_to_out
from app.development.schemas import (
    GoldenThreadComponentOut,
    Property360Out,
    SpecificationOut,
    TimelineEventOut,
)
from app.documents.schemas import DocumentOut
from app.operations.models import Repair
from app.platform.audit import AuditEvent

NOT_YET_AVAILABLE = [
    "compliance_and_safety (Sprint 15-17)",
    "stock_condition_and_planned_investment (Sprint 18)",
    "tenancy_and_lease (Sprint 19)",
    "rent_and_payments (Sprint 20)",
    "attention_signals (Sprint 21)",
    "ask_datalume (Sprint 22)",
]

def _components_for_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> list[Component]:
    space_ids = [
        row[0]
        for row in db.query(Space.id).filter(Space.property_id == property_id, Space.organisation_id == organisation_id)
    ]
    attachment_condition = (
        or_(Component.property_id == property_id, Component.space_id.in_(space_ids))
        if space_ids
        else Component.property_id == property_id
    )
    return (
        db.query(Component)
        .filter(Component.organisation_id == organisation_id, attachment_condition)
        .order_by(Component.created_at)
        .all()
    )


def _warranties_for(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID, component_ids: list[uuid.UUID]
) -> list[Warranty]:
    condition = (
        or_(Warranty.property_id == property_id, Warranty.component_id.in_(component_ids))
        if component_ids
        else Warranty.property_id == property_id
    )
    return db.query(Warranty).filter(Warranty.organisation_id == organisation_id, condition).all()


def _defects_for(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID, component_ids: list[uuid.UUID]
) -> list[Defect]:
    condition = (
        or_(Defect.property_id == property_id, Defect.component_id.in_(component_ids))
        if component_ids
        else Defect.property_id == property_id
    )
    return (
        db.query(Defect)
        .filter(Defect.organisation_id == organisation_id, condition)
        .order_by(Defect.reported_date.desc())
        .all()
    )


def _repairs_for(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID, component_ids: list[uuid.UUID]
) -> list[Repair]:
    condition = (
        or_(Repair.property_id == property_id, Repair.component_id.in_(component_ids))
        if component_ids
        else Repair.property_id == property_id
    )
    return (
        db.query(Repair)
        .filter(Repair.organisation_id == organisation_id, condition)
        .order_by(Repair.reported_date.desc())
        .all()
    )


def _timeline_for(
    db: Session,
    organisation_id: uuid.UUID,
    property_id: uuid.UUID,
    component_ids: list[uuid.UUID],
    repair_ids: list[uuid.UUID],
    limit: int = 50,
) -> list[TimelineEventOut]:
    entity_filter = (AuditEvent.entity_type == "property") & (AuditEvent.entity_id == str(property_id))
    if component_ids:
        entity_filter = or_(
            entity_filter,
            (AuditEvent.entity_type == "component") & (AuditEvent.entity_id.in_([str(c) for c in component_ids])),
        )
    if repair_ids:
        entity_filter = or_(
            entity_filter,
            (AuditEvent.entity_type == "repair") & (AuditEvent.entity_id.in_([str(r) for r in repair_ids])),
        )
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.organisation_id == organisation_id, entity_filter)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    actor_ids = {e.actor_user_id for e in events if e.actor_user_id}
    actors = {u.id: u.name for u in db.query(User).filter(User.id.in_(actor_ids))} if actor_ids else {}
    return [
        TimelineEventOut(
            action_code=e.action_code,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            actor_name=actors.get(e.actor_user_id),
            before=e.before,
            after=e.after,
            created_at=e.created_at,
        )
        for e in events
    ]


def get_property_360(db: Session, organisation_id: uuid.UUID, prop: Property) -> Property360Out:
    development = db.get(Development, prop.development_id) if prop.development_id else None
    building = db.get(Building, prop.building_id) if prop.building_id else None
    floor = db.get(Floor, prop.floor_id) if prop.floor_id else None

    components = _components_for_property(db, organisation_id, prop.id)
    component_type_names = component_type_names_for(db, components)
    component_views: list[GoldenThreadComponentOut] = [
        build_component_view(db, organisation_id, c, component_type_names) for c in components
    ]
    component_ids = [c.id for c in components]
    repairs = _repairs_for(db, organisation_id, prop.id, component_ids)
    repair_ids = [r.id for r in repairs]

    handover_record = (
        db.query(HandoverRecord)
        .filter(HandoverRecord.organisation_id == organisation_id, HandoverRecord.property_id == prop.id)
        .order_by(HandoverRecord.created_at.desc())
        .first()
    )

    # Data Health is "recomputed synchronously on read" by design
    # (app/data_health/models.py) — this view's caller commits the
    # refreshed findings same as GET /api/v1/data-health does, it's not
    # a special side effect Property 360 invented.
    _, data_health_results = run_data_health_checks(db, organisation_id)
    data_health_findings = [
        FindingOut(
            check_code=f.check_code,
            severity=f.severity.value,
            affected_entity_type=f.affected_entity_type,
            affected_entity_id=f.affected_entity_id,
            message=f.message,
        )
        for r in data_health_results
        for f in r.findings
        if f.affected_entity_type == "property" and f.affected_entity_id == str(prop.id)
    ]

    return Property360Out(
        property=property_to_out(db, organisation_id, prop),
        development=development_to_out(db, organisation_id, development) if development else None,
        building=building_to_out(db, organisation_id, building) if building else None,
        floor=floor,
        specifications=[
            SpecificationOut.model_validate(s) for s in current_specifications(db, organisation_id, "property", prop.id)
        ],
        evidence=[DocumentOut.model_validate(d) for d in evidence_for(db, organisation_id, "property", prop.id)],
        changes=changes_to_out(db, organisation_id, changes_for(db, organisation_id, "property", prop.id)),
        components=component_views,
        warranties=warranties_to_out(_warranties_for(db, organisation_id, prop.id, component_ids)),
        defects=_defects_for(db, organisation_id, prop.id, component_ids),
        repairs=repairs,
        handover_record=handover_record,
        data_health_findings=data_health_findings,
        timeline=_timeline_for(db, organisation_id, prop.id, component_ids, repair_ids),
        not_yet_available=NOT_YET_AVAILABLE,
    )
