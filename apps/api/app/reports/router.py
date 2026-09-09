"""Reporting & export — architecture/06-intelligence-layer.md §4.

**Board-level report types reuse the `/assurance-report` endpoint's own
`reports.board` gate.** Compliance Executive Summary and Board
Assurance both read get_board_assurance_report — the same data the
JSON `/assurance-report` endpoint already restricts to `reports.board`
(EXECUTIVE/OWNER/ADMIN). Letting any `reports.read` holder export that
same data as a file would be a permission regression through a side
door, so report creation and download both re-check `reports.board`
for exactly those two report types, on top of the router-level
`reports.read` every role already holds.

**Sprint 24 hardening**: architecture/09-security-testing-ops.md §1's
threat table lists "Unauthorised export of tenant data" with mitigation
"Report/export endpoints... are themselves audit events" — a real gap
this module had until now (every other write path in this codebase
calls record_audit_event; this one didn't). Both the request and the
download are recorded, since download is the actual export moment
(the same request-time job could be downloaded, and therefore
exported, more than once)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.rbac import role_has_permission
from app.core.db import get_db
from app.core.tenancy import AuthContext, require_permission
from app.integrations.storage import get_document_storage
from app.platform.audit import record_audit_event
from app.reports.models import ReportJob, ReportJobStatus, ReportType
from app.reports.render import CONTENT_TYPES, EXTENSIONS
from app.reports.schemas import CreateReportJobRequest, ReportJobOut
from app.reports.service import create_report_job, list_report_jobs

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

BOARD_LEVEL_REPORT_TYPES = {ReportType.BOARD_ASSURANCE, ReportType.COMPLIANCE_EXECUTIVE_SUMMARY}


def _require_report_type_permission(ctx: AuthContext, report_type: ReportType) -> None:
    if report_type in BOARD_LEVEL_REPORT_TYPES and not role_has_permission(ctx.role_code or "", "reports.board"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing permission: reports.board")


def _get_org_report_job(db: Session, organisation_id: uuid.UUID, report_job_id: uuid.UUID) -> ReportJob:
    job = (
        db.query(ReportJob)
        .filter(ReportJob.id == report_job_id, ReportJob.organisation_id == organisation_id)
        .first()
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report job not found")
    return job


@router.post("", response_model=ReportJobOut, status_code=status.HTTP_201_CREATED)
def request_report(
    payload: CreateReportJobRequest,
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    _require_report_type_permission(ctx, payload.report_type)
    job = create_report_job(
        db,
        ctx.organisation_id,
        ctx.user.id,
        report_type=payload.report_type,
        format=payload.format,
        building_id=payload.building_id,
        property_id=payload.property_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="report.requested",
        entity_type="report_job",
        entity_id=str(job.id),
        after={"report_type": job.report_type.value, "format": job.format.value, "filters": job.filters},
    )
    db.commit()
    return job


@router.get("", response_model=list[ReportJobOut])
def list_reports(
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return list_report_jobs(db, ctx.organisation_id)


@router.get("/{report_job_id}", response_model=ReportJobOut)
def get_report(
    report_job_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return _get_org_report_job(db, ctx.organisation_id, report_job_id)


@router.get("/{report_job_id}/download")
def download_report(
    report_job_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    job = _get_org_report_job(db, ctx.organisation_id, report_job_id)
    _require_report_type_permission(ctx, job.report_type)
    if job.status != ReportJobStatus.READY or job.storage_key is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Report is not ready yet (status: {job.status.value})")

    content = get_document_storage().read(job.storage_key)
    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="report.downloaded",
        entity_type="report_job",
        entity_id=str(job.id),
        after={"report_type": job.report_type.value, "format": job.format.value},
    )
    db.commit()

    extension = EXTENSIONS[job.format.value]
    filename = f"{job.report_type.value.lower()}.{extension}"
    return Response(
        content=content,
        media_type=CONTENT_TYPES[job.format.value],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
