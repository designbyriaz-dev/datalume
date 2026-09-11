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
    # Populated once the latest job's IMPORT step has finished processing
    # (worker/jobs/ingestion.py) — all None while AWAITING_MAPPING/MAPPED/
    # IMPORTING, since there's no result yet to report.
    rows_processed: int | None = None
    entities_created: int | None = None
    rows_failed: int | None = None
    importer_registered: bool | None = None
    error_summary: str | None = None


class ImportRowOut(BaseModel):
    row_number: int
    raw_data: dict
    status: str
    errors: list[str]

    model_config = {"from_attributes": True}


class ApplyMappingRequest(BaseModel):
    column_mapping: dict[str, str | None]
