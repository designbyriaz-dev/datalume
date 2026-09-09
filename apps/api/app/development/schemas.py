import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.development.models import ComponentStatus, PropertyStatus
from app.documents.schemas import DocumentOut


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
    REFERENCE -> ... chain from spec §29, built from existing tables only
    (architecture/03-development-domain.md §4: "compose, don't
    duplicate"). `not_yet_available` names the links in that chain with
    no canonical table yet — inspection (Sprint 16), handover (Sprint
    12) — so the UI can be honest about what this view does and doesn't
    cover yet, per spec §29's explicit constraint that storing this
    information does not by itself satisfy every legal Golden Thread
    obligation."""

    building_id: uuid.UUID
    building_reference: str
    building_name: str
    specifications: list[SpecificationOut]
    evidence: list[DocumentOut]
    changes: list[ChangeControlOut]
    external_references: dict[str, str]
    components: list[GoldenThreadComponentOut]
    not_yet_available: list[str]
