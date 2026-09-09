import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.data_health.schemas import FindingOut
from app.development.models import ComponentStatus, PropertyStatus
from app.documents.schemas import DocumentOut
from app.operations.schemas import RepairOut


class CreateDevelopmentRequest(BaseModel):
    name: str
    description: str | None = None
    address: str | None = None
    postcode: str | None = None
    planning_reference: str | None = None
    building_control_reference: str | None = None
    bsr_reference: str | None = None


class DevelopmentOut(BaseModel):
    id: uuid.UUID
    development_reference: str
    name: str
    description: str | None
    address: str | None
    postcode: str | None
    status: str
    planning_reference: str | None
    building_control_reference: str | None
    bsr_reference: str | None
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateBuildingRequest(BaseModel):
    name: str
    development_id: uuid.UUID | None = None
    building_type: str | None = None
    address: str | None = None
    storeys: int | None = None
    building_control_reference: str | None = None
    bsr_reference: str | None = None


class BuildingOut(BaseModel):
    id: uuid.UUID
    building_reference: str
    development_id: uuid.UUID | None
    name: str
    building_type: str | None
    address: str | None
    storeys: int | None
    status: str
    building_control_reference: str | None
    bsr_reference: str | None
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateFloorRequest(BaseModel):
    building_id: uuid.UUID
    name: str
    level_index: int | None = None


class FloorOut(BaseModel):
    id: uuid.UUID
    building_id: uuid.UUID
    name: str
    level_index: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreatePropertyRequest(BaseModel):
    address: str
    postcode: str | None = None
    uprn: str | None = None
    property_type: str | None = None
    status: PropertyStatus = PropertyStatus.OPERATIONAL
    development_id: uuid.UUID | None = None
    building_id: uuid.UUID | None = None
    floor_id: uuid.UUID | None = None


class PropertyOut(BaseModel):
    id: uuid.UUID
    property_reference: str
    address: str
    postcode: str | None
    uprn: str | None
    property_type: str | None
    status: str
    development_id: uuid.UUID | None
    building_id: uuid.UUID | None
    floor_id: uuid.UUID | None
    source_type: str
    source_dataset_id: uuid.UUID | None
    original_reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateSpaceRequest(BaseModel):
    name: str
    space_type: str | None = None
    property_id: uuid.UUID | None = None
    building_id: uuid.UUID | None = None


class SpaceOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID | None
    building_id: uuid.UUID | None
    name: str
    space_type: str | None
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FloorSummary(BaseModel):
    id: uuid.UUID
    name: str
    level_index: int | None
    property_count: int


class BuildingHierarchyOut(BaseModel):
    id: uuid.UUID
    building_reference: str
    name: str
    status: str
    floors: list[FloorSummary]
    unfloored_property_count: int  # properties on this building but no specific floor


class DevelopmentHierarchyOut(BaseModel):
    id: uuid.UUID
    development_reference: str
    name: str
    status: str
    buildings: list[BuildingHierarchyOut]
    unbuilt_property_count: int  # properties on this development but no specific building


class ComponentTypeOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    parent_type_id: uuid.UUID | None
    organisation_id: uuid.UUID | None  # None = global seeded type

    model_config = {"from_attributes": True}


class CreateComponentRequest(BaseModel):
    component_type_id: uuid.UUID
    component_subtype: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    installer: str | None = None
    installation_date: date | None = None
    commissioning_date: date | None = None
    warranty_start: date | None = None
    warranty_expiry: date | None = None
    expected_life_years: int | None = None
    status: ComponentStatus = ComponentStatus.ACTIVE
    development_id: uuid.UUID | None = None
    building_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    space_id: uuid.UUID | None = None
    parent_component_id: uuid.UUID | None = None


class ComponentOut(BaseModel):
    id: uuid.UUID
    component_reference: str
    component_type_id: uuid.UUID
    component_type_name: str
    component_subtype: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    installer: str | None
    installation_date: date | None
    commissioning_date: date | None
    warranty_start: date | None
    warranty_expiry: date | None
    expected_life_years: int | None
    indicative_replacement_date: date | None
    status: str
    development_id: uuid.UUID | None
    building_id: uuid.UUID | None
    property_id: uuid.UUID | None
    space_id: uuid.UUID | None
    parent_component_id: uuid.UUID | None
    source_type: str
    source_dataset_id: uuid.UUID | None
    original_reference: str | None
    created_at: datetime


class CreateSpecificationRequest(BaseModel):
    related_entity_type: str
    related_entity_id: uuid.UUID
    title: str
    description: str | None = None
    related_component_type: str | None = None
    effective_date: date | None = None
    source_document_id: uuid.UUID | None = None


class ReviseSpecificationRequest(BaseModel):
    revision: str
    title: str | None = None
    description: str | None = None
    related_component_type: str | None = None
    effective_date: date | None = None
    source_document_id: uuid.UUID | None = None


class SpecificationOut(BaseModel):
    id: uuid.UUID
    lineage_id: uuid.UUID
    specification_reference: str
    related_entity_type: str
    related_entity_id: str
    title: str
    description: str | None
    revision: str
    status: str
    effective_date: date | None
    superseded_date: date | None
    related_component_type: str | None
    source_document_id: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    source_type: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SpecificationDetailOut(SpecificationOut):
    versions: list[SpecificationOut]


class SubmitChangeControlRequest(BaseModel):
    specification_id: uuid.UUID
    proposed_value: dict
    reason: str
    impact_description: str | None = None


class ApproveChangeControlRequest(BaseModel):
    external_approval_reference: str | None = None


class ChangeControlOut(BaseModel):
    id: uuid.UUID
    change_reference: str
    specification_id: uuid.UUID
    related_entity_type: str
    related_entity_id: str
    previous_value: dict
    proposed_value: dict
    reason: str
    impact_description: str | None
    status: str
    approved_by: uuid.UUID | None
    approved_date: date | None
    implemented_specification_id: uuid.UUID | None
    external_approval_reference: str | None
    source_type: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HandoverRecordOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    development_id: uuid.UUID
    readiness_score_pct: float
    readiness_snapshot: list[dict]
    override_reason: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GoldenThreadResponsiblePartyOut(BaseModel):
    """architecture/03-development-domain.md §4: "responsible_party (from
    provenance/import metadata + contractor refs)" — there is no separate
    responsible-party table, this is composed from two things that already
    exist: who/how the record was created, and any CONTRACTOR_REFERENCE
    external reference recorded against it."""

    created_by_name: str | None
    created_by_email: str | None
    source_type: str
    source_system: str | None
    contractor_reference: str | None


class GoldenThreadComponentOut(BaseModel):
    id: uuid.UUID
    component_reference: str
    component_type_name: str
    status: str
    specifications: list[SpecificationOut]
    responsible_party: GoldenThreadResponsiblePartyOut
    evidence: list[DocumentOut]
    changes: list[ChangeControlOut]
    external_references: dict[str, str]


class GoldenThreadOut(BaseModel):
    """The composed BUILDING -> DESIGN/SPECIFICATION -> COMPONENT ->
    RESPONSIBLE PARTY -> EVIDENCE -> CHANGE -> APPROVAL/EXTERNAL
    REFERENCE -> HANDOVER -> ... chain from spec §29, built from existing
    tables only (architecture/03-development-domain.md §4: "compose,
    don't duplicate"). HANDOVER is Sprint 12's own addition
    (`HandoverRecord` rows for properties under this building).
    `not_yet_available` names the one remaining link with no canonical
    table yet — inspection (Sprint 16) — so the UI can be honest about
    what this view does and doesn't cover yet, per spec §29's explicit
    constraint that storing this information does not by itself satisfy
    every legal Golden Thread obligation."""

    building_id: uuid.UUID
    building_reference: str
    building_name: str
    specifications: list[SpecificationOut]
    evidence: list[DocumentOut]
    changes: list[ChangeControlOut]
    handover_records: list[HandoverRecordOut]
    external_references: dict[str, str]
    components: list[GoldenThreadComponentOut]
    not_yet_available: list[str]


class CreateDefectRequest(BaseModel):
    category: str
    description: str
    reported_date: date
    severity: str = "MEDIUM"
    contractor: str | None = None
    responsible_party: str | None = None
    target_date: date | None = None
    estimated_cost_pence: int | None = None
    warranty_related: bool = False
    development_id: uuid.UUID | None = None
    building_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None


class UpdateDefectStatusRequest(BaseModel):
    status: str
    completion_date: date | None = None
    actual_cost_pence: int | None = None


class DefectOut(BaseModel):
    id: uuid.UUID
    defect_reference: str
    development_id: uuid.UUID | None
    building_id: uuid.UUID | None
    property_id: uuid.UUID | None
    component_id: uuid.UUID | None
    category: str
    description: str
    severity: str
    reported_date: date
    contractor: str | None
    responsible_party: str | None
    target_date: date | None
    completion_date: date | None
    status: str
    estimated_cost_pence: int | None
    actual_cost_pence: int | None
    warranty_related: bool
    source_type: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DefectsByKeyOut(BaseModel):
    key: str
    count: int


class DefectsIntelligenceOut(BaseModel):
    """architecture 03 §8 / spec §35 — a fixed set of aggregate reads
    over the defect register, not a scored/weighted engine like Data
    Health (Sprint 5) or Component Lifecycle: the spec's own examples
    ("Block A has 42 defects. 18 relate to Contractor X...") are plain
    counts and averages, so that's what this composes — every number
    here is directly re-derivable from GET /api/v1/defects, nothing is
    stored separately."""

    total_count: int
    open_count: int
    overdue_count: int
    warranty_related_count: int
    by_contractor: list[DefectsByKeyOut]
    by_category: list[DefectsByKeyOut]
    by_component_type: list[DefectsByKeyOut]
    repeat_categories: list[DefectsByKeyOut]
    total_estimated_cost_pence: int
    total_actual_cost_pence: int
    average_resolution_days: float | None


class CreateWarrantyRequest(BaseModel):
    provider: str
    warranty_type: str
    start_date: date
    expiry_date: date
    terms_reference: str | None = None
    document_id: uuid.UUID | None = None
    development_id: uuid.UUID | None = None
    building_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None


class WarrantyOut(BaseModel):
    id: uuid.UUID
    warranty_reference: str
    provider: str
    development_id: uuid.UUID | None
    building_id: uuid.UUID | None
    property_id: uuid.UUID | None
    component_id: uuid.UUID | None
    warranty_type: str
    start_date: date
    expiry_date: date
    terms_reference: str | None
    document_id: uuid.UUID | None
    status: str
    is_expired: bool
    days_until_expiry: int
    source_type: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdatePropertyStatusRequest(BaseModel):
    status: str


class HandoverCheckOut(BaseModel):
    check_code: str
    label: str
    weight: float
    applicable_count: int
    failing_count: int
    pass_ratio: float
    missing_items: list[str]


class HandoverReadinessOut(BaseModel):
    development_id: uuid.UUID
    score_pct: float
    threshold_pct: float
    ready: bool
    checks: list[HandoverCheckOut]
    missing: list[str]


class AuthoriseHandoverRequest(BaseModel):
    override_reason: str | None = None


class HandoverReadinessWeightOut(BaseModel):
    check_code: str
    label: str
    weight: float


class UpdateHandoverReadinessWeightRequest(BaseModel):
    weight: float


class TimelineEventOut(BaseModel):
    action_code: str
    entity_type: str
    entity_id: str | None
    actor_name: str | None
    before: dict | None
    after: dict | None
    created_at: datetime


class Property360Out(BaseModel):
    """architecture/03-development-domain.md all sections, spec §41.
    Composes everything spec §41 asks for that has a canonical table as
    of Sprint 14 — Property Information, Development History, Building/
    Block, Components (with Golden Thread's own per-component bundle,
    app/development/composition.py), Golden Thread-equivalent evidence/
    specs/changes at the property's own level, Handover, Warranties,
    Defects, Repairs, Data Health. Compliance & Safety, Stock Condition,
    Planned Investment, Tenancy/Lease, Rent & Payments, Attention
    Signals and Ask DataLume have no canonical data yet — named
    explicitly in not_yet_available rather than omitted silently, same
    pattern as Golden Thread's own list."""

    property: PropertyOut
    development: DevelopmentOut | None
    building: BuildingOut | None
    floor: FloorOut | None
    specifications: list[SpecificationOut]
    evidence: list[DocumentOut]
    changes: list[ChangeControlOut]
    components: list[GoldenThreadComponentOut]
    warranties: list[WarrantyOut]
    defects: list[DefectOut]
    repairs: list[RepairOut]
    handover_record: HandoverRecordOut | None
    data_health_findings: list[FindingOut]
    timeline: list[TimelineEventOut]
    not_yet_available: list[str]


class PortfolioStatusCountOut(BaseModel):
    key: str
    count: int


class DevelopmentReadinessSummaryOut(BaseModel):
    development_id: uuid.UUID
    development_reference: str
    name: str
    score_pct: float


class PortfolioSummaryOut(BaseModel):
    """Portfolio rollups — roadmap Sprint 13 "portfolio rollups", spec
    §41's portfolio-level counterpart to Property 360. Every number here
    is directly re-derivable from the entity list/detail endpoints
    already built (properties, components, defects, warranties, data
    health) — nothing new is stored, this is a read-composition exactly
    like Golden Thread and Property 360."""

    total_properties: int
    total_developments: int
    total_buildings: int
    total_components: int
    properties_by_status: list[PortfolioStatusCountOut]
    data_health_score_pct: float
    open_defects_count: int
    overdue_defects_count: int
    warranties_expiring_within_90_days_count: int
    development_readiness: list[DevelopmentReadinessSummaryOut]
