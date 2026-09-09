"""Compliance Framework write paths — architecture/04-operations-domain.md
§3. Same "manual entry calls the same function" reasoning as every
other *_service.py in this codebase, even though nothing imports a CSV
path into this yet."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Building, Component, Property
from app.documents.models import Document
from app.operations.compliance.models import (
    ComplianceAction,
    ComplianceActionStatus,
    ComplianceDomain,
    ComplianceRequirement,
    ComplianceStatusConfig,
    Inspection,
    InspectionResult,
    RequirementApplicability,
)
from app.operations.compliance.seed import ensure_compliance_catalog_seeded, get_or_create_default_framework
from app.platform.audit import record_audit_event

APPLICABILITY_ENTITY_TYPES = ("building", "property", "component")


class ComplianceNotFoundError(ValueError):
    """A given domain_id/requirement_id/entity doesn't exist in this
    organisation — the router maps this to a 404."""


class UnsupportedApplicabilityEntityTypeError(ValueError):
    """entity_type isn't one of the three spec §46 targets
    (building/property/component) — the router maps this to a 400."""


class RequirementAlreadySupersededError(ValueError):
    """Attempted to create a new version from a requirement row that
    isn't the current one — the router maps this to a 400."""


class InvalidComplianceActionTransitionError(ValueError):
    """The requested status transition isn't allowed from a compliance
    action's current status — the router maps this to a 400."""


class DuplicateRequirementCodeError(ValueError):
    """A current (non-superseded) requirement with this (domain, code)
    already exists — the router maps this to a 400. Versioning that
    requirement (POST .../versions) is how you change it; a second
    top-level create with the same code would silently corrupt the
    version-lineage lookup, which matches requirements by (domain_id,
    code) rather than a separate lineage_id column."""


def _get_org_domain(db: Session, organisation_id: uuid.UUID, domain_id: uuid.UUID) -> ComplianceDomain:
    domain = (
        db.query(ComplianceDomain)
        .filter(
            ComplianceDomain.id == domain_id,
            (ComplianceDomain.organisation_id == organisation_id) | (ComplianceDomain.organisation_id.is_(None)),
        )
        .first()
    )
    if domain is None:
        raise ComplianceNotFoundError(f"Compliance domain {domain_id} not found")
    return domain


def _get_org_requirement(db: Session, organisation_id: uuid.UUID, requirement_id: uuid.UUID) -> ComplianceRequirement:
    requirement = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.id == requirement_id,
            (ComplianceRequirement.organisation_id == organisation_id)
            | (ComplianceRequirement.organisation_id.is_(None)),
        )
        .first()
    )
    if requirement is None:
        raise ComplianceNotFoundError(f"Compliance requirement {requirement_id} not found")
    return requirement


def _validate_applicability_entity(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> None:
    if entity_type == "building":
        found = db.query(Building.id).filter(Building.id == entity_id, Building.organisation_id == organisation_id).first()
    elif entity_type == "property":
        found = db.query(Property.id).filter(Property.id == entity_id, Property.organisation_id == organisation_id).first()
    elif entity_type == "component":
        found = (
            db.query(Component.id).filter(Component.id == entity_id, Component.organisation_id == organisation_id).first()
        )
    else:
        raise UnsupportedApplicabilityEntityTypeError(
            f"entity_type must be one of {APPLICABILITY_ENTITY_TYPES}, got {entity_type!r}"
        )
    if found is None:
        raise ComplianceNotFoundError(f"{entity_type} {entity_id} not found")


def list_domains(db: Session, organisation_id: uuid.UUID) -> list[ComplianceDomain]:
    ensure_compliance_catalog_seeded(db)
    return (
        db.query(ComplianceDomain)
        .filter((ComplianceDomain.organisation_id == organisation_id) | (ComplianceDomain.organisation_id.is_(None)))
        .order_by(ComplianceDomain.name)
        .all()
    )


def create_domain(
    db: Session, organisation_id: uuid.UUID, *, code: str, name: str, description: str | None, actor_user_id: uuid.UUID | None
) -> ComplianceDomain:
    framework = get_or_create_default_framework(db)
    domain = ComplianceDomain(
        organisation_id=organisation_id, framework_id=framework.id, code=code, name=name, description=description
    )
    db.add(domain)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="compliance_domain.created",
        entity_type="compliance_domain",
        entity_id=str(domain.id),
        after={"code": code, "name": name},
    )
    return domain


def list_requirements(
    db: Session, organisation_id: uuid.UUID, *, domain_id: uuid.UUID | None = None, current_only: bool = True
) -> list[ComplianceRequirement]:
    query = db.query(ComplianceRequirement).filter(
        (ComplianceRequirement.organisation_id == organisation_id) | (ComplianceRequirement.organisation_id.is_(None))
    )
    if domain_id is not None:
        query = query.filter(ComplianceRequirement.domain_id == domain_id)
    if current_only:
        query = query.filter(ComplianceRequirement.superseded_date.is_(None))
    return query.order_by(ComplianceRequirement.code).all()


def create_requirement(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    domain_id: uuid.UUID,
    code: str,
    title: str,
    description: str | None,
    cadence: str | None,
    effective_date: date,
    actor_user_id: uuid.UUID | None,
    hard_deadline: bool = True,
) -> ComplianceRequirement:
    _get_org_domain(db, organisation_id, domain_id)
    duplicate = (
        db.query(ComplianceRequirement.id)
        .filter(
            ComplianceRequirement.organisation_id == organisation_id,
            ComplianceRequirement.domain_id == domain_id,
            ComplianceRequirement.code == code,
            ComplianceRequirement.superseded_date.is_(None),
        )
        .first()
    )
    if duplicate is not None:
        raise DuplicateRequirementCodeError(
            f"A current requirement with code {code!r} already exists in this domain — "
            "add a new version of it instead of creating a duplicate"
        )

    requirement = ComplianceRequirement(
        organisation_id=organisation_id,
        domain_id=domain_id,
        code=code,
        title=title,
        description=description,
        cadence=cadence,
        version=1,
        effective_date=effective_date,
        hard_deadline=hard_deadline,
    )
    db.add(requirement)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="compliance_requirement.created",
        entity_type="compliance_requirement",
        entity_id=str(requirement.id),
        after={"code": code, "title": title, "cadence": cadence},
    )
    return requirement


def create_requirement_version(
    db: Session,
    organisation_id: uuid.UUID,
    previous: ComplianceRequirement,
    *,
    title: str | None,
    description: str | None,
    cadence: str | None,
    effective_date: date,
    actor_user_id: uuid.UUID | None,
    hard_deadline: bool | None = None,
) -> ComplianceRequirement:
    """"do not hard-code permanent interpretations of evolving Building
    Regulations" (spec §31) — a new version is a new row, the prior one
    only ever marked superseded, same append-only pattern as
    Specification (Sprint 9)."""
    if previous.superseded_date is not None:
        raise RequirementAlreadySupersededError(
            "This is not the current version — create a new version from the latest one instead"
        )

    new_version = ComplianceRequirement(
        organisation_id=previous.organisation_id,
        domain_id=previous.domain_id,
        code=previous.code,
        title=title if title is not None else previous.title,
        description=description if description is not None else previous.description,
        cadence=cadence if cadence is not None else previous.cadence,
        version=previous.version + 1,
        effective_date=effective_date,
        hard_deadline=hard_deadline if hard_deadline is not None else previous.hard_deadline,
    )
    db.add(new_version)
    db.flush()

    previous.superseded_date = effective_date

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="compliance_requirement.new_version",
        entity_type="compliance_requirement",
        entity_id=str(new_version.id),
        before={"superseded_requirement_id": str(previous.id)},
        after={"version": new_version.version},
    )
    return new_version


def create_applicability(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    requirement_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    applicable_from: date,
    basis: str | None,
    actor_user_id: uuid.UUID | None,
) -> RequirementApplicability:
    _get_org_requirement(db, organisation_id, requirement_id)
    _validate_applicability_entity(db, organisation_id, entity_type, entity_id)

    applicability = RequirementApplicability(
        organisation_id=organisation_id,
        requirement_id=requirement_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        applicable_from=applicable_from,
        basis=basis,
    )
    db.add(applicability)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="requirement_applicability.created",
        entity_type="requirement_applicability",
        entity_id=str(applicability.id),
        after={"requirement_id": str(requirement_id), "entity_type": entity_type, "entity_id": str(entity_id)},
    )
    return applicability


def end_applicability(
    db: Session,
    organisation_id: uuid.UUID,
    applicability: RequirementApplicability,
    *,
    applicable_to: date,
    actor_user_id: uuid.UUID | None,
) -> RequirementApplicability:
    applicability.applicable_to = applicable_to
    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="requirement_applicability.ended",
        entity_type="requirement_applicability",
        entity_id=str(applicability.id),
        after={"applicable_to": str(applicable_to)},
    )
    return applicability


def _get_org_document(db: Session, organisation_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.query(Document).filter(Document.id == document_id, Document.organisation_id == organisation_id).first()
    if document is None:
        raise ComplianceNotFoundError(f"Document {document_id} not found")
    return document


def list_inspections(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
) -> list[Inspection]:
    query = db.query(Inspection).filter(Inspection.organisation_id == organisation_id)
    if entity_type is not None:
        query = query.filter(Inspection.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(Inspection.entity_id == str(entity_id))
    if requirement_id is not None:
        query = query.filter(Inspection.requirement_id == requirement_id)
    return query.order_by(Inspection.inspection_date.desc()).all()


def create_inspection(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    requirement_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    inspector: str,
    inspection_date: date,
    result: str,
    next_due_date: date | None,
    evidence_document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> Inspection:
    _get_org_requirement(db, organisation_id, requirement_id)
    _validate_applicability_entity(db, organisation_id, entity_type, entity_id)
    if evidence_document_id is not None:
        _get_org_document(db, organisation_id, evidence_document_id)

    inspection = Inspection(
        organisation_id=organisation_id,
        requirement_id=requirement_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        inspector=inspector,
        inspection_date=inspection_date,
        result=InspectionResult(result),
        next_due_date=next_due_date,
        evidence_document_id=evidence_document_id,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(inspection)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="inspection.recorded",
        entity_type="inspection",
        entity_id=str(inspection.id),
        after={"requirement_id": str(requirement_id), "result": result, "next_due_date": str(next_due_date)},
    )
    return inspection


def list_compliance_actions(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    action_status: str | None = None,
) -> list[ComplianceAction]:
    query = db.query(ComplianceAction).filter(ComplianceAction.organisation_id == organisation_id)
    if entity_type is not None:
        query = query.filter(ComplianceAction.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(ComplianceAction.entity_id == str(entity_id))
    if requirement_id is not None:
        query = query.filter(ComplianceAction.requirement_id == requirement_id)
    if action_status is not None:
        query = query.filter(ComplianceAction.status == ComplianceActionStatus(action_status))
    return query.order_by(ComplianceAction.deadline).all()


def create_compliance_action(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    requirement_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    description: str,
    deadline: date,
    inspection_id: uuid.UUID | None,
    evidence_document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> ComplianceAction:
    _get_org_requirement(db, organisation_id, requirement_id)
    _validate_applicability_entity(db, organisation_id, entity_type, entity_id)
    if inspection_id is not None:
        found = (
            db.query(Inspection.id)
            .filter(Inspection.id == inspection_id, Inspection.organisation_id == organisation_id)
            .first()
        )
        if found is None:
            raise ComplianceNotFoundError(f"Inspection {inspection_id} not found")
    if evidence_document_id is not None:
        _get_org_document(db, organisation_id, evidence_document_id)

    action = ComplianceAction(
        organisation_id=organisation_id,
        inspection_id=inspection_id,
        requirement_id=requirement_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        description=description,
        deadline=deadline,
        status=ComplianceActionStatus.OPEN,
        evidence_document_id=evidence_document_id,
        source_type=SourceType.MANUAL,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(action)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="compliance_action.raised",
        entity_type="compliance_action",
        entity_id=str(action.id),
        after={"requirement_id": str(requirement_id), "deadline": str(deadline)},
    )
    return action


COMPLIANCE_ACTION_TRANSITIONS: dict[ComplianceActionStatus, tuple[ComplianceActionStatus, ...]] = {
    ComplianceActionStatus.OPEN: (ComplianceActionStatus.COMPLETED, ComplianceActionStatus.CANCELLED),
    ComplianceActionStatus.COMPLETED: (),
    ComplianceActionStatus.CANCELLED: (),
}


def update_compliance_action_status(
    db: Session,
    organisation_id: uuid.UUID,
    action: ComplianceAction,
    *,
    new_status: str,
    completed_date: date | None,
    evidence_document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> ComplianceAction:
    target = ComplianceActionStatus(new_status)
    allowed = COMPLIANCE_ACTION_TRANSITIONS.get(action.status, ())
    if target not in allowed:
        raise InvalidComplianceActionTransitionError(f"Cannot move a compliance action from {action.status.value} to {target.value}")
    if evidence_document_id is not None:
        _get_org_document(db, organisation_id, evidence_document_id)

    previous_status = action.status
    action.status = target
    if target == ComplianceActionStatus.COMPLETED:
        action.completed_date = completed_date or date.today()
    if evidence_document_id is not None:
        action.evidence_document_id = evidence_document_id

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="compliance_action.status_changed",
        entity_type="compliance_action",
        entity_id=str(action.id),
        before={"status": previous_status.value},
        after={"status": target.value},
    )
    return action


def get_or_create_status_config(db: Session, organisation_id: uuid.UUID) -> ComplianceStatusConfig:
    config = (
        db.query(ComplianceStatusConfig)
        .filter(ComplianceStatusConfig.organisation_id == organisation_id)
        .with_for_update()
        .first()
    )
    if config is not None:
        return config
    config = ComplianceStatusConfig(organisation_id=organisation_id)
    db.add(config)
    db.flush()
    return config


def set_status_config(
    db: Session, organisation_id: uuid.UUID, *, due_soon_days: int | None, never_assessed_grace_days: int | None
) -> ComplianceStatusConfig:
    config = get_or_create_status_config(db, organisation_id)
    if due_soon_days is not None:
        config.due_soon_days = due_soon_days
    if never_assessed_grace_days is not None:
        config.never_assessed_grace_days = never_assessed_grace_days
    db.flush()
    return config
