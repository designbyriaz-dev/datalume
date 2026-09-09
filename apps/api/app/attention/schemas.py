import uuid
from datetime import datetime

from pydantic import BaseModel


class AttentionRuleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    domain_scope: str
    rule_definition: dict
    severity_default: str
    is_active: bool

    model_config = {"from_attributes": True}


class UpdateAttentionRuleRequest(BaseModel):
    is_active: bool | None = None
    rule_definition: dict | None = None


class AttentionSignalOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    rule_code: str
    entity_type: str
    entity_id: str
    severity: str
    detected_at: datetime
    explanation: dict
    status: str


class UpdateSignalStatusRequest(BaseModel):
    status: str


class AttentionScanResultOut(BaseModel):
    rules_evaluated: int
    signals_created: int
    signals_refreshed: int
