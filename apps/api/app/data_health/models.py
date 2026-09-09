"""DataHealthFinding — architecture/02-data-platform.md §5.

Deterministic, versioned, transparent: every finding traces to a named,
individually-testable rule function (app/data_health/rules.py), never an
opaque score. Recomputed synchronously on read for now (no job queue
yet — same simplification as the ingestion pipeline, Sprint 3) rather
than on a debounced trigger from entity changes."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FindingSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DataHealthFinding(Base):
    __tablename__ = "data_health_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    check_code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity))
    affected_entity_type: Mapped[str] = mapped_column(String(64))
    affected_entity_id: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(500))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
