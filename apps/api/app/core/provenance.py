"""ProvenanceMixin — architecture/02-data-platform.md §1.

Every canonical domain entity (developments, properties, components,
repairs, ...) inherits this so "where did this record come from?" is
always answerable from the row itself. Nothing consumes it for real yet
— the first canonical domain tables land in Sprint 5+ (see
architecture/10-roadmap-and-acceptance.md) — but the ingestion pipeline
built in Sprint 3 (app/ingestion/) exists specifically to populate these
fields, so the mixin is defined and tested now rather than bolted on
later. See app/tests/test_provenance.py for a mixin-level test against a
throwaway table, since there's no real consumer table yet.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column


class SourceType(str, enum.Enum):
    MANUAL = "MANUAL"
    FILE_UPLOAD = "FILE_UPLOAD"
    API = "API"
    SCHEDULED_IMPORT = "SCHEDULED_IMPORT"
    INTEGRATION = "INTEGRATION"
    SYSTEM_GENERATED = "SYSTEM_GENERATED"


class ProvenanceMixin:
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True
    )
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_jobs.id"), nullable=True)
    original_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
