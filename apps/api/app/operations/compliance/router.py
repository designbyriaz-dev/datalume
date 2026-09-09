"""Compliance Framework — architecture/04-operations-domain.md §3, spec
§45-46. Gated by `operations.compliance` for writes — a narrower
permission than `operations.write`, held only by COMPLIANCE_MANAGER and
BUILDING_SAFETY_MANAGER in RBAC (not REPAIRS_MANAGER/PROPERTY_MANAGER,
who can operate day-to-day repairs but shouldn't be reshaping the
compliance framework itself)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.operations.compliance.models import (
    ComplianceDomain,
    ComplianceFramework,
    ComplianceRequirement,
    RequirementApplicability,
)
from app.operations.compliance.schemas import (
    ComplianceDomainOut,
    ComplianceFrameworkOut,
    ComplianceRequirementDetailOut,
    ComplianceRequirementOut,
    CreateApplicabilityRequest,
    CreateComplianceDomainRequest,
    CreateComplianceRequirementRequest,
    EndApplicabilityRequest,
    RequirementApplicabilityOut,
    ReviseComplianceRequirementRequest,
)
from app.operations.compliance.seed import ensure_compliance_catalog_seeded
from app.operations.compliance.service import (
    ComplianceNotFoundError,
    DuplicateRequirementCodeError,
    RequirementAlreadySupersededError,
    UnsupportedApplicabilityEntityTypeError,
    create_applicability,
    create_domain,
    create_requirement,
    create_requirement_version,
    end_applicability,
    list_domains,
    list_requirements,
)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compliance requirement not found")
    return requirement


def _get_org_applicability(db: Session, organisation_id: uuid.UUID, applicability_id: uuid.UUID) -> RequirementApplicability:
    applicability = (
        db.query(RequirementApplicability)
        .filter(RequirementApplicability.id == applicability_id, RequirementApplicability.organisation_id == organisation_id)
        .first()
    )
    if applicability is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement applicability not found")
    return applicability


@router.get("/frameworks", response_model=list[ComplianceFrameworkOut])
def get_frameworks(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    ensure_compliance_catalog_seeded(db)
    db.commit()
    return (
        db.query(ComplianceFramework)
        .filter((ComplianceFramework.organisation_id == ctx.organisation_id) | (ComplianceFramework.organisation_id.is_(None)))
        .all()
    )


@router.get("/domains", response_model=list[ComplianceDomainOut])
def get_domains(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    domains = list_domains(db, ctx.organisation_id)
    db.commit()
    return domains


@router.post("/domains", response_model=ComplianceDomainOut, status_code=status.HTTP_201_CREATED)
def add_domain(
    payload: CreateComplianceDomainRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    domain = create_domain(
        db,
        ctx.organisation_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        actor_user_id=ctx.user.id,
    )
    db.commit()
    db.refresh(domain)
    return domain


@router.get("/requirements", response_model=list[ComplianceRequirementOut])
def get_requirements(
    domain_id: uuid.UUID | None = None,
    current_only: bool = True,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_requirements(db, ctx.organisation_id, domain_id=domain_id, current_only=current_only)


@router.post("/requirements", response_model=ComplianceRequirementOut, status_code=status.HTTP_201_CREATED)
def add_requirement(
    payload: CreateComplianceRequirementRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        requirement = create_requirement(
            db,
            ctx.organisation_id,
            domain_id=payload.domain_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            cadence=payload.cadence,
            effective_date=payload.effective_date,
            actor_user_id=ctx.user.id,
        )
    except ComplianceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DuplicateRequirementCodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get("/requirements/{requirement_id}", response_model=ComplianceRequirementDetailOut)
def get_requirement(
    requirement_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    requirement = _get_org_requirement(db, ctx.organisation_id, requirement_id)
    versions = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.domain_id == requirement.domain_id,
            ComplianceRequirement.code == requirement.code,
            (ComplianceRequirement.organisation_id == ctx.organisation_id)
            | (ComplianceRequirement.organisation_id.is_(None)),
        )
        .order_by(ComplianceRequirement.version)
        .all()
    )
    return ComplianceRequirementDetailOut(
        **ComplianceRequirementOut.model_validate(requirement).model_dump(), versions=versions
    )


@router.post("/requirements/{requirement_id}/versions", response_model=ComplianceRequirementOut, status_code=status.HTTP_201_CREATED)
def add_requirement_version(
    requirement_id: uuid.UUID,
    payload: ReviseComplianceRequirementRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    previous = _get_org_requirement(db, ctx.organisation_id, requirement_id)
    try:
        new_version = create_requirement_version(
            db,
            ctx.organisation_id,
            previous,
            title=payload.title,
            description=payload.description,
            cadence=payload.cadence,
            effective_date=payload.effective_date,
            actor_user_id=ctx.user.id,
        )
    except RequirementAlreadySupersededError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(new_version)
    return new_version


@router.post("/applicability", response_model=RequirementApplicabilityOut, status_code=status.HTTP_201_CREATED)
def add_applicability(
    payload: CreateApplicabilityRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        applicability = create_applicability(
            db,
            ctx.organisation_id,
            requirement_id=payload.requirement_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            applicable_from=payload.applicable_from,
            basis=payload.basis,
            actor_user_id=ctx.user.id,
        )
    except UnsupportedApplicabilityEntityTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ComplianceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(applicability)
    return applicability


@router.get("/applicability", response_model=list[RequirementApplicabilityOut])
def get_applicability(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(RequirementApplicability).filter(RequirementApplicability.organisation_id == ctx.organisation_id)
    if entity_type is not None:
        query = query.filter(RequirementApplicability.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(RequirementApplicability.entity_id == str(entity_id))
    if requirement_id is not None:
        query = query.filter(RequirementApplicability.requirement_id == requirement_id)
    return query.order_by(RequirementApplicability.applicable_from.desc()).all()


@router.post("/applicability/{applicability_id}/end", response_model=RequirementApplicabilityOut)
def end_applicability_endpoint(
    applicability_id: uuid.UUID,
    payload: EndApplicabilityRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    applicability = _get_org_applicability(db, ctx.organisation_id, applicability_id)
    applicability = end_applicability(
        db,
        ctx.organisation_id,
        applicability,
        applicable_to=payload.applicable_to,
        actor_user_id=ctx.user.id,
    )
    db.commit()
    db.refresh(applicability)
    return applicability
