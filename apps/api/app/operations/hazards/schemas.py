import uuid
from datetime import date

from pydantic import BaseModel


class CreateHazardRequest(BaseModel):
    property_id: uuid.UUID
    hazard_type: str
    reported_date: date
    severity: str = "MEDIUM"


class UpdateHazardStatusRequest(BaseModel):
    status: str
    investigation_status: str | None = None
    findings: str | None = None
    deadline: date | None = None


class HazardOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    hazard_type: str
    reported_date: date
    severity: str
    investigation_status: str
    findings: str | None
    deadline: date | None
    status: str

    model_config = {"from_attributes": True}


class CreateHazardActionRequest(BaseModel):
    description: str
    deadline: date
    evidence_document_id: uuid.UUID | None = None


class UpdateHazardActionStatusRequest(BaseModel):
    status: str
    completed_date: date | None = None
    evidence_document_id: uuid.UUID | None = None


class HazardActionOut(BaseModel):
    id: uuid.UUID
    hazard_id: uuid.UUID
    description: str
    deadline: date
    status: str
    completed_date: date | None
    evidence_document_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class RepeatHazardSignalOut(BaseModel):
    property_id: uuid.UUID
    hazard_type: str
    hazard_count: int
    window_months: int
    threshold: int
    hazard_ids: list[uuid.UUID]


class HazardRuleConfigOut(BaseModel):
    rule_code: str
    window_months: int
    threshold: int

    model_config = {"from_attributes": True}


class UpdateHazardRuleConfigRequest(BaseModel):
    window_months: int | None = None
    threshold: int | None = None
