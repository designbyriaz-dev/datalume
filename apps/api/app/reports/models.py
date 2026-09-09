"""Reporting & export — architecture/06-intelligence-layer.md §4, spec
§59's named report types. A report is a rendering target, not a
separate data path: every report_type's content is composed entirely
from already-built service-layer functions (get_portfolio_summary,
compute_handover_readiness, get_board_assurance_report,
collection_rate/arrears_for_lease) — see reports/content.py. Nothing in
this package computes a new number.

`ReportJob` follows Sprint 3's `ImportJob` shape (id, organisation_id,
status, started_at/finished_at, error) almost exactly, since it's the
same kind of thing: a row tracking one async unit of work. Unlike
ImportJob (which had no real queue to run on and stayed synchronous,
documented as an honest scope gap), report generation runs on this
codebase's now-real worker loop (app/worker/main.py, built for real in
Sprint 21) — architecture §4 explicitly requires background generation
for anything beyond a small dataset, and the infrastructure to do that
for real now exists, so this sprint uses it rather than repeating
Sprint 3's synchronous workaround.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReportType(str, enum.Enum):
    DEVELOPMENT_SUMMARY = "DEVELOPMENT_SUMMARY"
    HANDOVER_READINESS = "HANDOVER_READINESS"
    COMPLIANCE_EXECUTIVE_SUMMARY = "COMPLIANCE_EXECUTIVE_SUMMARY"
    BOARD_ASSURANCE = "BOARD_ASSURANCE"
    COMMERCIAL_PORTFOLIO = "COMMERCIAL_PORTFOLIO"


class ReportFormat(str, enum.Enum):
    PDF = "PDF"
    XLSX = "XLSX"
    CSV = "CSV"


class ReportJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"


class ReportJob(Base):
    """`filters` holds the report_type-specific scoping the request was
    made with (building_id/property_id for the two compliance report
    types, period_start/period_end for Commercial Portfolio's collection
    rate window) — kept as one JSON bag rather than a column per
    possible filter, same reasoning as AttentionRule.rule_definition:
    which filters apply depends entirely on report_type, so a fixed
    column set would be mostly-NULL for every row."""

    __tablename__ = "report_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType))
    format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[ReportJobStatus] = mapped_column(Enum(ReportJobStatus), default=ReportJobStatus.PENDING)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Python-side default (microsecond resolution), not server_default=
    # func.now() — SQLite's CURRENT_TIMESTAMP is second-granular, which
    # made "most recent first" ordering unstable for two jobs requested
    # within the same second in tests. Postgres gets the same behaviour
    # either way; this is strictly more precise there too.
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
