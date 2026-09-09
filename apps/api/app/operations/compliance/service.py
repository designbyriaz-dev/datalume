"""Compliance Framework write paths — architecture/04-operations-domain.md
§3. Same "manual entry calls the same function" reasoning as every
other *_service.py in this codebase, even though nothing imports a CSV
path into this yet."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.development.models import Building, Component, Property
from app.operations.compliance.models import ComplianceDomain, ComplianceRequirement, RequirementApplicability
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
