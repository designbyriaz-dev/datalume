import uuid
from datetime import datetime

from pydantic import BaseModel

from app.identifiers.models import ExternalReferenceType


class RecordExternalReferenceRequest(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    reference_type: ExternalReferenceType
    value: str
    source: str | None = None


class ExternalReferenceOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: str
    reference_type: str
    value: str
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferencePatternOut(BaseModel):
    entity_type: str
    pattern: str
    next_sequence: int

    model_config = {"from_attributes": True}


class UpdateReferencePatternRequest(BaseModel):
    pattern: str
