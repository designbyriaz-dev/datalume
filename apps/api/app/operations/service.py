"""Shared create/update functions for Repairs — same "manual entry and
import call the same function" reasoning as
app/development/service.py's own docstring, even though no CSV importer
exists for repairs yet (nothing in the roadmap calls for one this
sprint)."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Component, Property
from app.identifiers.service import generate_reference
from app.operations.models import Repair, RepairPriority, RepairRuleConfig, RepairStatus
from app.platform.audit import record_audit_event


class RepairNotFoundError(ValueError):
    """A given property_id/component_id doesn't exist in this
    organisation — the router maps this to a 404."""


class InvalidRepairTransitionError(ValueError):
    """The requested status transition isn't allowed from a repair's
    current status — the router maps this to a 400."""


REPAIR_TRANSITIONS: dict[RepairStatus, tuple[RepairStatus, ...]] = {
    RepairStatus.REPORTED: (RepairStatus.SCHEDULED, RepairStatus.CANCELLED),
    RepairStatus.SCHEDULED: (RepairStatus.IN_PROGRESS, RepairStatus.CANCELLED),
    RepairStatus.IN_PROGRESS: (RepairStatus.COMPLETED, RepairStatus.CANCELLED),
    RepairStatus.COMPLETED: (),
    RepairStatus.CANCELLED: (),
}


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = db.query(Property).filter(Property.id == property_id, Property.organisation_id == organisation_id).first()
    if prop is None:
        raise RepairNotFoundError(f"Property {property_id} not found")
    return prop


def _get_org_component(db: Session, organisation_id: uuid.UUID, component_id: uuid.UUID) -> Component:
    component = (
        db.query(Component).filter(Component.id == component_id, Component.organisation_id == organisation_id).first()
    )
    if component is None:
        raise RepairNotFoundError(f"Component {component_id} not found")
    return component


def _get_org_repair(db: Session, organisation_id: uuid.UUID, repair_id: uuid.UUID) -> Repair:
    repair = db.query(Repair).filter(Repair.id == repair_id, Repair.organisation_id == organisation_id).first()
    if repair is None:
        raise RepairNotFoundError(f"Repair {repair_id} not found")
    return repair


def create_repair(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    property_id: uuid.UUID,
    component_id: uuid.UUID | None = None,
    category: str,
    description: str,
    reported_date: date,
    priority: str = "ROUTINE",
    contractor: str | None = None,
    cost_pence: int | None = None,
    source_type: SourceType = SourceType.MANUAL,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Repair:
    _get_org_property(db, organisation_id, property_id)
    if component_id is not None:
        _get_org_component(db, organisation_id, component_id)

    priority_enum = RepairPriority(priority)
    repair = Repair(
        organisation_id=organisation_id,
        repair_reference=generate_reference(db, organisation_id, "REPAIR"),
        property_id=property_id,
        component_id=component_id,
        category=category,
        description=description,
        priority=priority_enum,
        is_emergency=priority_enum == RepairPriority.EMERGENCY,
        reported_date=reported_date,
        contractor=contractor,
        cost_pence=cost_pence,
        status=RepairStatus.REPORTED,
        source_type=source_type,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(repair)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="repair.reported",
        entity_type="repair",
        entity_id=str(repair.id),
        after={"repair_reference": repair.repair_reference, "category": category, "priority": priority},
    )
    return repair


def update_repair_status(
    db: Session,
    organisation_id: uuid.UUID,
    repair: Repair,
    *,
    new_status: str,
    completed_date: date | None = None,
    cost_pence: int | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Repair:
    target = RepairStatus(new_status)
    allowed = REPAIR_TRANSITIONS.get(repair.status, ())
    if target not in allowed:
        raise InvalidRepairTransitionError(f"Cannot move a repair from {repair.status.value} to {target.value}")

    previous_status = repair.status
    repair.status = target
    if target == RepairStatus.COMPLETED:
        repair.completed_date = completed_date or date.today()
    if cost_pence is not None:
        repair.cost_pence = cost_pence

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="repair.status_changed",
        entity_type="repair",
        entity_id=str(repair.id),
        before={"status": previous_status.value},
        after={"status": target.value},
    )
    return repair


def get_or_create_repair_rule_config(
    db: Session, organisation_id: uuid.UUID, rule_code: str, defaults: dict
) -> RepairRuleConfig:
    config = (
        db.query(RepairRuleConfig)
        .filter(RepairRuleConfig.organisation_id == organisation_id, RepairRuleConfig.rule_code == rule_code)
        .with_for_update()
        .first()
    )
    if config is not None:
        return config
    config = RepairRuleConfig(organisation_id=organisation_id, rule_code=rule_code, **defaults)
    db.add(config)
    db.flush()
    return config


def set_repair_rule_config(
    db: Session, organisation_id: uuid.UUID, rule_code: str, updates: dict
) -> RepairRuleConfig:
    from app.operations.repeat_repair import RULE_DEFAULTS

    if rule_code not in RULE_DEFAULTS:
        raise RepairNotFoundError(f"Unknown repair rule_code: {rule_code}")
    config = get_or_create_repair_rule_config(db, organisation_id, rule_code, RULE_DEFAULTS[rule_code])
    for field, value in updates.items():
        if value is not None:
            setattr(config, field, value)
    db.flush()
    return config


def list_repair_rule_configs(db: Session, organisation_id: uuid.UUID) -> list[RepairRuleConfig]:
    from app.operations.repeat_repair import RULE_DEFAULTS

    for rule_code, defaults in RULE_DEFAULTS.items():
        get_or_create_repair_rule_config(db, organisation_id, rule_code, defaults)
    return db.query(RepairRuleConfig).filter(RepairRuleConfig.organisation_id == organisation_id).all()
