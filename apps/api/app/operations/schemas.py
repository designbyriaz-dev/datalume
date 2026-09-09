import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CreateRepairRequest(BaseModel):
    property_id: uuid.UUID
    component_id: uuid.UUID | None = None
    category: str
    description: str
    reported_date: date
    priority: str = "ROUTINE"
    contractor: str | None = None
    cost_pence: int | None = None


class UpdateRepairStatusRequest(BaseModel):
    status: str
    completed_date: date | None = None
    cost_pence: int | None = None


class RepairOut(BaseModel):
    id: uuid.UUID
    repair_reference: str
    property_id: uuid.UUID
    component_id: uuid.UUID | None
    category: str
    description: str
    priority: str
    is_emergency: bool
    reported_date: date
    contractor: str | None
    completed_date: date | None
    cost_pence: int | None
    status: str
    source_type: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RepairRuleConfigOut(BaseModel):
    rule_code: str
    window_months: int | None
    threshold: int | None
    threshold_ratio: float | None
    min_installed_base: int | None


class UpdateRepairRuleConfigRequest(BaseModel):
    window_months: int | None = None
    threshold: int | None = None
    threshold_ratio: float | None = None
    min_installed_base: int | None = None


class RepeatRepairSignalOut(BaseModel):
    """architecture/04-operations-domain.md §2: "Every signal produced
    stores its inputs... so Explainability can answer 'what records
    support this' without recomputation drift" — repair_ids/window/
    threshold are carried on the signal itself, computed fresh on every
    read (same "deterministic, computed at read time" approach as Data
    Health and Handover Readiness), not persisted separately."""

    property_id: uuid.UUID
    repair_count: int
    window_months: int
    threshold: int
    repair_ids: list[uuid.UUID]


class RepeatFailureSignalOut(BaseModel):
    component_id: uuid.UUID
    repair_count: int
    window_months: int
    threshold: int
    repair_ids: list[uuid.UUID]


class ModelTrendSignalOut(BaseModel):
    component_type_id: uuid.UUID
    manufacturer: str
    model: str
    installed_count: int
    failed_count: int
    failure_ratio: float
    threshold_ratio: float
    component_ids: list[uuid.UUID]


class RepairsByKeyOut(BaseModel):
    key: str
    count: int


class RepairsIntelligenceOut(BaseModel):
    """architecture/04-operations-domain.md §1, spec §43 — a fixed set
    of aggregate reads, same "not a scored engine" reasoning as Defects
    Intelligence (Sprint 11): the spec's own examples are plain counts
    and averages."""

    total_count: int
    open_count: int
    completed_count: int
    emergency_count: int
    by_category: list[RepairsByKeyOut]
    by_contractor: list[RepairsByKeyOut]
    total_cost_pence: int
    average_completion_days: float | None
    repeat_repair_properties: list[RepeatRepairSignalOut]
    repeat_failure_components: list[RepeatFailureSignalOut]
