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


class ReviseComplianceRequirementRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    cadence: str | None = None
    effective_date: date


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
