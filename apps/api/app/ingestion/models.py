"""Dataset / ImportJob / ImportRow — architecture/02-data-platform.md §2.

The upload pipeline (UPLOAD -> VALIDATE -> UNDERSTAND -> MAP -> REVIEW ->
IMPORT -> ANALYSE) is a staging table (import_rows), not a
parse-and-insert-directly endpoint — see pipeline.py for why, and its
module docstring for what's genuinely built vs. simplified in Sprint 3.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DatasetStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    VALIDATED = "VALIDATED"
    MAPPED = "MAPPED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


class ImportJobStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    AWAITING_MAPPING = "AWAITING_MAPPING"
    MAPPED = "MAPPED"
    IMPORTING = "IMPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ImportRowStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    IMPORTED = "IMPORTED"
    SKIPPED = "SKIPPED"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String(255))
    dataset_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus), default=DatasetStatus.UPLOADED)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Object-storage key for the uploaded file. Architecture 02 §4 calls
    # for a real `documents` table (versioned, FK'd here as
    # source_file_document_id) — that lands in Sprint 4. Until then this
    # is a plain key, not a document reference.
    source_file_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Denormalized from Dataset.organisation_id — RLS policies need it on
    # every tenant table directly; deriving it via a dataset_id join in
    # every policy is both slower and harder to get right. Set once at
    # creation from the parent dataset, never updated independently.
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"))
    status: Mapped[ImportJobStatus] = mapped_column(Enum(ImportJobStatus), default=ImportJobStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    column_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    import_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_jobs.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[ImportRowStatus] = mapped_column(Enum(ImportRowStatus), default=ImportRowStatus.PENDING)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    mapped_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapped_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MappingTemplate(Base):
    """Reusable column->field mapping per organisation + dataset_type, so a
    repeat import from the same source system doesn't need re-mapping —
    architecture/02-data-platform.md §2 step 4."""

    __tablename__ = "mapping_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    dataset_type: Mapped[str] = mapped_column(String(64))
    column_mapping: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
