"""Report job lifecycle — create (PENDING), and process (called by the
worker loop, app/worker/jobs/report_generation.py). Building the
content and rendering it to bytes are kept in content.py/render.py so
this module is purely the job-state machine, the same separation
compliance/status_engine.py (pure) vs router.py (HTTP) already uses."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.storage import get_document_storage
from app.organisations.models import Organisation
from app.reports.content import (
    build_board_assurance_report,
    build_commercial_portfolio_report,
    build_compliance_executive_summary_report,
    build_development_summary_report,
    build_handover_readiness_report,
)
from app.reports.models import ReportFormat, ReportJob, ReportJobStatus, ReportType
from app.reports.render import EXTENSIONS, RENDERERS


def create_report_job(
    db: Session,
    organisation_id: uuid.UUID,
    requested_by: uuid.UUID,
    *,
    report_type: ReportType,
    format: ReportFormat,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ReportJob:
    filters: dict = {}
    if building_id is not None:
        filters["building_id"] = str(building_id)
    if property_id is not None:
        filters["property_id"] = str(property_id)
    if period_start is not None:
        filters["period_start"] = period_start.isoformat()
    if period_end is not None:
        filters["period_end"] = period_end.isoformat()

    job = ReportJob(
        organisation_id=organisation_id,
        report_type=report_type,
        format=format,
        filters=filters,
        status=ReportJobStatus.PENDING,
        requested_by=requested_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_report_jobs(db: Session, organisation_id: uuid.UUID) -> list[ReportJob]:
    return (
        db.query(ReportJob)
        .filter(ReportJob.organisation_id == organisation_id)
        .order_by(ReportJob.requested_at.desc())
        .all()
    )


def _build_content(db: Session, job: ReportJob, organisation_name: str):
    filters = job.filters or {}
    building_id = uuid.UUID(filters["building_id"]) if "building_id" in filters else None
    property_id = uuid.UUID(filters["property_id"]) if "property_id" in filters else None

    if job.report_type == ReportType.DEVELOPMENT_SUMMARY:
        return build_development_summary_report(db, job.organisation_id, organisation_name)
    if job.report_type == ReportType.HANDOVER_READINESS:
        return build_handover_readiness_report(db, job.organisation_id, organisation_name)
    if job.report_type == ReportType.COMPLIANCE_EXECUTIVE_SUMMARY:
        return build_compliance_executive_summary_report(
            db, job.organisation_id, organisation_name, building_id=building_id, property_id=property_id
        )
    if job.report_type == ReportType.BOARD_ASSURANCE:
        return build_board_assurance_report(
            db, job.organisation_id, organisation_name, building_id=building_id, property_id=property_id
        )
    if job.report_type == ReportType.COMMERCIAL_PORTFOLIO:
        period_end = date.fromisoformat(filters["period_end"]) if "period_end" in filters else date.today()
        period_start = (
            date.fromisoformat(filters["period_start"]) if "period_start" in filters else period_end.replace(day=1)
        )
        return build_commercial_portfolio_report(
            db, job.organisation_id, organisation_name, period_start=period_start, period_end=period_end
        )
    raise ValueError(f"Unknown report_type: {job.report_type}")


def process_report_job(db: Session, job_id: uuid.UUID) -> ReportJob:
    """Idempotent-ish: only ever picks up a job still PENDING (the
    worker's own query already filters on that), so re-invoking this on
    an already-RUNNING/READY/FAILED job is a no-op that returns the job
    as found rather than reprocessing it."""

    job = db.get(ReportJob, job_id)
    if job is None or job.status != ReportJobStatus.PENDING:
        return job

    job.status = ReportJobStatus.RUNNING
    db.commit()

    try:
        organisation = db.get(Organisation, job.organisation_id)
        organisation_name = organisation.name if organisation else "Unknown organisation"
        content = _build_content(db, job, organisation_name)
        file_bytes = RENDERERS[job.format.value](content)

        extension = EXTENSIONS[job.format.value]
        storage_key = f"reports/{job.organisation_id}/{job.id}.{extension}"
        get_document_storage().save(storage_key, file_bytes)

        job.status = ReportJobStatus.READY
        job.storage_key = storage_key
        job.file_size_bytes = len(file_bytes)
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001 — reported on the job row, not swallowed
        job.status = ReportJobStatus.FAILED
        job.error_message = str(exc)[:1024]
        job.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)
    return job
