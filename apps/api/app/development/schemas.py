import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.development.models import ComponentStatus, PropertyStatus


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
