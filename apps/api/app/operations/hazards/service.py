"""Hazards, damp & mould — architecture/04-operations-domain.md §5, spec
§49. Same "manual entry calls the same function" reasoning as every
other *_service.py in this codebase."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Property
from app.documents.models import Document
from app.operations.hazards.models import (
    Hazard,
    HazardAction,
    HazardActionStatus,
    HazardInvestigationStatus,
    HazardRuleConfig,
    HazardSeverity,
    HazardStatus,
)
from app.platform.audit import record_audit_event


class HazardNotFoundError(ValueError):
    """A given property_id/hazard_id/document_id doesn't exist in this
    organisation — the router maps this to a 404."""


class InvalidHazardTransitionError(ValueError):
    """The requested status transition isn't allowed from a hazard's
    current status — the router maps this to a 400."""


class InvalidHazardActionTransitionError(ValueError):
    """The requested status transition isn't allowed from a hazard
    action's current status — the router maps this to a 400."""


HAZARD_TRANSITIONS: dict[HazardStatus, tuple[HazardStatus, ...]] = {
    HazardStatus.REPORTED: (HazardStatus.TRIAGED,),
    HazardStatus.TRIAGED: (HazardStatus.INVESTIGATING,),
    HazardStatus.INVESTIGATING: (HazardStatus.INVESTIGATED,),
    HazardStatus.INVESTIGATED: (HazardStatus.ACTION_IN_PROGRESS, HazardStatus.FOLLOW_UP, HazardStatus.CLOSED),
    HazardStatus.ACTION_IN_PROGRESS: (HazardStatus.FOLLOW_UP, HazardStatus.CLOSED),
    HazardStatus.FOLLOW_UP: (HazardStatus.CLOSED, HazardStatus.ACTION_IN_PROGRESS),
    HazardStatus.CLOSED: (),
}

HAZARD_ACTION_TRANSITIONS: dict[HazardActionStatus, tuple[HazardActionStatus, ...]] = {
    HazardActionStatus.OPEN: (HazardActionStatus.COMPLETED, HazardActionStatus.CANCELLED),
    HazardActionStatus.COMPLETED: (),
    HazardActionStatus.CANCELLED: (),
}


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = db.query(Property).filter(Property.id == property_id, Property.organisation_id == organisation_id).first()
    if prop is None:
        raise HazardNotFoundError(f"Property {property_id} not found")
    return prop


def _get_org_document(db: Session, organisation_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.query(Document).filter(Document.id == document_id, Document.organisation_id == organisation_id).first()
    if document is None:
        raise HazardNotFoundError(f"Document {document_id} not found")
    return document


def create_hazard(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    property_id: uuid.UUID,
    hazard_type: str,
    reported_date: date,
    severity: str,
    actor_user_id: uuid.UUID | None,
) -> Hazard:
    _get_org_property(db, organisation_id, property_id)

    hazard = Hazard(
        organisation_id=organisation_id,
        property_id=property_id,
        hazard_type=hazard_type,
        reported_date=reported_date,
        severity=HazardSeverity(severity),
        investigation_status=HazardInvestigationStatus.PENDING,
        status=HazardStatus.REPORTED,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(hazard)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="hazard.reported",
        entity_type="hazard",
        entity_id=str(hazard.id),
        after={"hazard_type": hazard_type, "severity": severity},
    )
    return hazard


def update_hazard_status(
    db: Session,
    organisation_id: uuid.UUID,
    hazard: Hazard,
    *,
    new_status: str,
    investigation_status: str | None,
    findings: str | None,
    deadline: date | None,
    actor_user_id: uuid.UUID | None,
) -> Hazard:
    target = HazardStatus(new_status)
    allowed = HAZARD_TRANSITIONS.get(hazard.status, ())
    if target not in allowed:
        raise InvalidHazardTransitionError(f"Cannot move a hazard from {hazard.status.value} to {target.value}")

    previous_status = hazard.status
    hazard.status = target
    if investigation_status is not None:
        hazard.investigation_status = HazardInvestigationStatus(investigation_status)
    if findings is not None:
        hazard.findings = findings
    if deadline is not None:
        hazard.deadline = deadline

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="hazard.status_changed",
        entity_type="hazard",
        entity_id=str(hazard.id),
        before={"status": previous_status.value},
        after={"status": target.value},
    )
    return hazard


def create_hazard_action(
    db: Session,
    organisation_id: uuid.UUID,
    hazard: Hazard,
    *,
    description: str,
    deadline: date,
    evidence_document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> HazardAction:
    if evidence_document_id is not None:
        _get_org_document(db, organisation_id, evidence_document_id)

    action = HazardAction(
        organisation_id=organisation_id,
        hazard_id=hazard.id,
        description=description,
        deadline=deadline,
        status=HazardActionStatus.OPEN,
        evidence_document_id=evidence_document_id,
    )
    db.add(action)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="hazard_action.raised",
        entity_type="hazard_action",
        entity_id=str(action.id),
        after={"hazard_id": str(hazard.id), "deadline": str(deadline)},
    )
    return action


def update_hazard_action_status(
    db: Session,
    organisation_id: uuid.UUID,
    action: HazardAction,
    *,
    new_status: str,
    completed_date: date | None,
    evidence_document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> HazardAction:
    target = HazardActionStatus(new_status)
    allowed = HAZARD_ACTION_TRANSITIONS.get(action.status, ())
    if target not in allowed:
        raise InvalidHazardActionTransitionError(f"Cannot move a hazard action from {action.status.value} to {target.value}")
    if evidence_document_id is not None:
        _get_org_document(db, organisation_id, evidence_document_id)

    previous_status = action.status
    action.status = target
    if target == HazardActionStatus.COMPLETED:
        action.completed_date = completed_date or date.today()
    if evidence_document_id is not None:
        action.evidence_document_id = evidence_document_id

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="hazard_action.status_changed",
        entity_type="hazard_action",
        entity_id=str(action.id),
        before={"status": previous_status.value},
        after={"status": target.value},
    )
    return action


def get_or_create_hazard_rule_config(
    db: Session, organisation_id: uuid.UUID, rule_code: str, defaults: dict
) -> HazardRuleConfig:
    config = (
        db.query(HazardRuleConfig)
        .filter(HazardRuleConfig.organisation_id == organisation_id, HazardRuleConfig.rule_code == rule_code)
        .with_for_update()
        .first()
    )
    if config is not None:
        return config
    config = HazardRuleConfig(organisation_id=organisation_id, rule_code=rule_code, **defaults)
    db.add(config)
    db.flush()
    return config


def set_hazard_rule_config(db: Session, organisation_id: uuid.UUID, rule_code: str, updates: dict) -> HazardRuleConfig:
    from app.operations.hazards.repeat_hazard import RULE_DEFAULTS

    if rule_code not in RULE_DEFAULTS:
        raise HazardNotFoundError(f"Unknown hazard rule_code: {rule_code}")
    config = get_or_create_hazard_rule_config(db, organisation_id, rule_code, RULE_DEFAULTS[rule_code])
    for field, value in updates.items():
        if value is not None:
            setattr(config, field, value)
    db.flush()
    return config


def list_hazard_rule_configs(db: Session, organisation_id: uuid.UUID) -> list[HazardRuleConfig]:
    from app.operations.hazards.repeat_hazard import RULE_DEFAULTS

    for rule_code, defaults in RULE_DEFAULTS.items():
        get_or_create_hazard_rule_config(db, organisation_id, rule_code, defaults)
    return db.query(HazardRuleConfig).filter(HazardRuleConfig.organisation_id == organisation_id).all()
