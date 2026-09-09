import uuid
from datetime import datetime

from pydantic import BaseModel

from app.development.models import PropertyStatus


class CreatePropertyRequest(BaseModel):
    address: str
    postcode: str | None = None
    uprn: str | None = None
    property_type: str | None = None
    status: PropertyStatus = PropertyStatus.OPERATIONAL


class PropertyOut(BaseModel):
    id: uuid.UUID
    property_reference: str
    address: str
    postcode: str | None
    uprn: str | None
    property_type: str | None
    status: str
    source_type: str
    source_dataset_id: uuid.UUID | None
    original_reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateSpaceRequest(BaseModel):
    name: str
    space_type: str | None = None


class SpaceOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    name: str
    space_type: str | None
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
