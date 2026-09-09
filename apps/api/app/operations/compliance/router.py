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
    ComplianceAction,
    ComplianceDomain,
    ComplianceFramework,
    ComplianceRequirement,
    Inspection,
    RequirementApplicability,
)
from app.operations.compliance.assurance import get_board_assurance_report
from app.operations.compliance.schemas import (
    BoardAssuranceReportOut,
    ComplianceActionOut,
    ComplianceDomainOut,
    ComplianceFrameworkOut,
    ComplianceRequirementDetailOut,
    ComplianceRequirementOut,
    ComplianceStatusConfigOut,
    ComplianceStatusOut,
    CreateApplicabilityRequest,
    CreateComplianceActionRequest,
    CreateComplianceDomainRequest,
    CreateComplianceRequirementRequest,
    CreateInspectionRequest,
    EndApplicabilityRequest,
    InspectionOut,
    RequirementApplicabilityOut,
    ReviseComplianceRequirementRequest,
    UpdateComplianceActionStatusRequest,
    UpdateComplianceStatusConfigRequest,
)
from app.operations.compliance.seed import ensure_compliance_catalog_seeded
from app.operations.compliance.service import (
    ComplianceNotFoundError,
    DuplicateRequirementCodeError,
    InvalidComplianceActionTransitionError,
    RequirementAlreadySupersededError,
    UnsupportedApplicabilityEntityTypeError,
    create_applicability,
    create_compliance_action,
    create_domain,
    create_inspection,
    create_requirement,
    create_requirement_version,
    end_applicability,
    get_or_create_status_config,
    list_compliance_actions,
    list_domains,
    list_inspections,
    list_requirements,
    set_status_config,
    update_compliance_action_status,
)
from app.operations.compliance.status_engine import ComplianceStatusResult, compliance_status, list_compliance_statuses_for_entity

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


def _status_result_to_out(result: ComplianceStatusResult) -> ComplianceStatusOut:
    return ComplianceStatusOut(
        status=result.status.value,
        requirement_id=result.requirement_id,
        domain_id=result.domain_id,
        entity_type=result.entity_type,
        entity_id=result.entity_id,
        latest_inspection=InspectionOut.model_validate(result.latest_inspection) if result.latest_inspection else None,
        open_action=ComplianceActionOut.model_validate(result.open_action) if result.open_action else None,
        days_to_due=result.days_to_due,
    )


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


def _get_org_inspection(db: Session, organisation_id: uuid.UUID, inspection_id: uuid.UUID) -> Inspection:
    inspection = (
        db.query(Inspection).filter(Inspection.id == inspection_id, Inspection.organisation_id == organisation_id).first()
    )
    if inspection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")
    return inspection


def _get_org_action(db: Session, organisation_id: uuid.UUID, action_id: uuid.UUID) -> ComplianceAction:
    action = (
        db.query(ComplianceAction)
        .filter(ComplianceAction.id == action_id, ComplianceAction.organisation_id == organisation_id)
        .first()
    )
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compliance action not found")
    return action


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
            hard_deadline=payload.hard_deadline,
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
            hard_deadline=payload.hard_deadline,
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


@router.get("/inspections", response_model=list[InspectionOut])
def get_inspections(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_inspections(db, ctx.organisation_id, entity_type=entity_type, entity_id=entity_id, requirement_id=requirement_id)


@router.post("/inspections", response_model=InspectionOut, status_code=status.HTTP_201_CREATED)
def add_inspection(
    payload: CreateInspectionRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        inspection = create_inspection(
            db,
            ctx.organisation_id,
            requirement_id=payload.requirement_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            inspector=payload.inspector,
            inspection_date=payload.inspection_date,
            result=payload.result,
            next_due_date=payload.next_due_date,
            evidence_document_id=payload.evidence_document_id,
            actor_user_id=ctx.user.id,
        )
    except UnsupportedApplicabilityEntityTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ComplianceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(inspection)
    return inspection


@router.get("/actions", response_model=list[ComplianceActionOut])
def get_actions(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    action_status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_compliance_actions(
        db,
        ctx.organisation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        requirement_id=requirement_id,
        action_status=action_status,
    )


@router.post("/actions", response_model=ComplianceActionOut, status_code=status.HTTP_201_CREATED)
def add_action(
    payload: CreateComplianceActionRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    try:
        action = create_compliance_action(
            db,
            ctx.organisation_id,
            requirement_id=payload.requirement_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            description=payload.description,
            deadline=payload.deadline,
            inspection_id=payload.inspection_id,
            evidence_document_id=payload.evidence_document_id,
            actor_user_id=ctx.user.id,
        )
    except UnsupportedApplicabilityEntityTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ComplianceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(action)
    return action


@router.post("/actions/{action_id}/status", response_model=ComplianceActionOut)
def update_action_status_endpoint(
    action_id: uuid.UUID,
    payload: UpdateComplianceActionStatusRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    action = _get_org_action(db, ctx.organisation_id, action_id)
    try:
        update_compliance_action_status(
            db,
            ctx.organisation_id,
            action,
            new_status=payload.status,
            completed_date=payload.completed_date,
            evidence_document_id=payload.evidence_document_id,
            actor_user_id=ctx.user.id,
        )
    except InvalidComplianceActionTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ComplianceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(action)
    return action


@router.get("/status", response_model=ComplianceStatusOut)
def get_status(
    entity_type: str,
    entity_id: uuid.UUID,
    requirement_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    requirement = _get_org_requirement(db, ctx.organisation_id, requirement_id)
    result = compliance_status(db, ctx.organisation_id, entity_type=entity_type, entity_id=entity_id, requirement=requirement)
    return _status_result_to_out(result)


@router.get("/statuses", response_model=list[ComplianceStatusOut])
def get_statuses(
    entity_type: str,
    entity_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    results = list_compliance_statuses_for_entity(db, ctx.organisation_id, entity_type, entity_id)
    return [_status_result_to_out(r) for r in results]


@router.get("/status-config", response_model=ComplianceStatusConfigOut)
def get_status_config(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    config = get_or_create_status_config(db, ctx.organisation_id)
    db.commit()
    db.refresh(config)
    return config


@router.patch("/status-config", response_model=ComplianceStatusConfigOut)
def update_status_config(
    payload: UpdateComplianceStatusConfigRequest,
    ctx: AuthContext = Depends(require_permission("operations.compliance")),
    db: Session = Depends(get_db),
):
    config = set_status_config(
        db, ctx.organisation_id, due_soon_days=payload.due_soon_days, never_assessed_grace_days=payload.never_assessed_grace_days
    )
    db.commit()
    db.refresh(config)
    return config


@router.get("/assurance-report", response_model=BoardAssuranceReportOut)
def get_assurance_report(
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(require_permission("reports.board")),
    db: Session = Depends(get_db),
):
    return get_board_assurance_report(db, ctx.organisation_id, building_id=building_id, property_id=property_id)
