import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.reports.models import ReportFormat, ReportJobStatus, ReportType


class CreateReportJobRequest(BaseModel):
    report_type: ReportType
    format: ReportFormat
    building_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    period_start: date | None = None
    period_end: date | None = None


class ReportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: ReportType
    format: ReportFormat
    filters: dict
    status: ReportJobStatus
    requested_by: uuid.UUID
    requested_at: datetime
    completed_at: datetime | None
    error_message: str | None
    file_size_bytes: int | None
