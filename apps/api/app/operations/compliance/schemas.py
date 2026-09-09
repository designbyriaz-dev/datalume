import uuid
from datetime import date

from pydantic import BaseModel


class ComplianceFrameworkOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    name: str
    version: int

    model_config = {"from_attributes": True}


class CreateComplianceDomainRequest(BaseModel):
    code: str
    name: str
    description: str | None = None


class ComplianceDomainOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    framework_id: uuid.UUID
    code: str
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class CreateComplianceRequirementRequest(BaseModel):
    domain_id: uuid.UUID
    code: str
    title: str
    description: str | None = None
    cadence: str | None = None
    effective_date: date
    hard_deadline: bool = True


class ReviseComplianceRequirementRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    cadence: str | None = None
    effective_date: date
    hard_deadline: bool | None = None


class ComplianceRequirementOut(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    domain_id: uuid.UUID
    code: str
    title: str
    description: str | None
    cadence: str | None
    version: int
    effective_date: date
    superseded_date: date | None
    hard_deadline: bool

    model_config = {"from_attributes": True}


class ComplianceRequirementDetailOut(ComplianceRequirementOut):
    versions: list[ComplianceRequirementOut]


class CreateApplicabilityRequest(BaseModel):
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    applicable_from: date
    basis: str | None = None


class EndApplicabilityRequest(BaseModel):
    applicable_to: date


class RequirementApplicabilityOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: str
    applicable_from: date
    applicable_to: date | None
    basis: str | None

    model_config = {"from_attributes": True}


class CreateInspectionRequest(BaseModel):
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    inspector: str
    inspection_date: date
    result: str
    next_due_date: date | None = None
    evidence_document_id: uuid.UUID | None = None


class InspectionOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: str
    inspector: str
    inspection_date: date
    result: str
    next_due_date: date | None
    evidence_document_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class CreateComplianceActionRequest(BaseModel):
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    description: str
    deadline: date
    inspection_id: uuid.UUID | None = None
    evidence_document_id: uuid.UUID | None = None


class UpdateComplianceActionStatusRequest(BaseModel):
    status: str
    completed_date: date | None = None
    evidence_document_id: uuid.UUID | None = None


class ComplianceActionOut(BaseModel):
    id: uuid.UUID
    inspection_id: uuid.UUID | None
    requirement_id: uuid.UUID
    entity_type: str
    entity_id: str
    description: str
    deadline: date
    status: str
    completed_date: date | None
    evidence_document_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ComplianceStatusConfigOut(BaseModel):
    due_soon_days: int
    never_assessed_grace_days: int

    model_config = {"from_attributes": True}


class UpdateComplianceStatusConfigRequest(BaseModel):
    due_soon_days: int | None = None
    never_assessed_grace_days: int | None = None


class ComplianceStatusOut(BaseModel):
    """One deterministic status per (entity, requirement) — architecture
    §4. Carries the evidence the status was computed from so a caller
    (UI or, later, Ask DataLume) can explain *why* without recomputing
    or re-deriving anything itself."""

    status: str
    requirement_id: uuid.UUID
    domain_id: uuid.UUID
    entity_type: str
    entity_id: str
    latest_inspection: InspectionOut | None
    open_action: ComplianceActionOut | None
    days_to_due: int | None


class BoardAssuranceDomainSummaryOut(BaseModel):
    domain_id: uuid.UUID
    domain_code: str
    domain_name: str
    status_counts: dict[str, int]
    open_actions: int
    overdue_actions: int


class BoardAssuranceReportOut(BaseModel):
    """Spec item 57: "a read-only rollup of compliance_status counts +
    open/overdue compliance_actions + hazard status, grouped by domain
    and property/portfolio" — a view over status_engine.py's own
    deterministic output, never a scored or narrated summary of its
    own."""

    domains: list[BoardAssuranceDomainSummaryOut]
    total_open_actions: int
    total_overdue_actions: int
    hazard_status_counts: dict[str, int]
    open_hazard_severity_counts: dict[str, int]
