import uuid
from datetime import datetime

from pydantic import BaseModel

from app.ingestion.field_dictionary import FieldSpec


class UploadResponse(BaseModel):
    dataset_id: uuid.UUID
    import_job_id: uuid.UUID
    row_count: int
    proposed_mapping: dict[str, str | None]
    field_dictionary: list[FieldSpec]
    suggested_mapping_from_template: bool


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    dataset_type: str
    status: str
    row_count: int
    uploaded_at: datetime
    source_file_document_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class DatasetDetailOut(DatasetOut):
    latest_job_status: str | None
    row_status_counts: dict[str, int]


class ImportRowOut(BaseModel):
    row_number: int
    raw_data: dict
    status: str
    errors: list[str]

    model_config = {"from_attributes": True}


class ApplyMappingRequest(BaseModel):
    column_mapping: dict[str, str | None]


class ImportResultOut(BaseModel):
    rows_processed: int
    entities_created: int
    rows_failed: int
    importer_registered: bool
