"""Report generation — architecture/06-intelligence-layer.md §4:
"Report generation runs as a background job for anything beyond a small
dataset... never generated synchronously in the request/response
cycle." Unlike the Attention Engine's nightly scan (attention_scan.py),
report jobs are on-demand — a user requests one, and it should complete
in seconds, not by the next 2am scan — so worker/main.py polls for
PENDING jobs on every heartbeat tick rather than once a day.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.tenancy import TenantScopedSession
from app.organisations.models import Organisation
from app.reports.models import ReportJob, ReportJobStatus
from app.reports.service import process_report_job


@dataclass
class ReportGenerationResult:
    jobs_processed: int
    jobs_failed: int


def process_pending_report_jobs(db: Session, *, limit: int = 20) -> ReportGenerationResult:
    # report_jobs is RLS-protected (migration 0021) — a single global
    # "find every PENDING job regardless of organisation" query is
    # exactly what RLS exists to block without a tenant context, and
    # there is no single org to scope this whole call to (that's the
    # point: this worker tick serves every organisation). organisations
    # itself carries no RLS policy (deliberately global), so it's safe
    # to list every org id here, then scope to each in turn — the same
    # per-organisation loop run_attention_scan_for_all_organisations
    # already uses, and for the same reason.
    jobs_processed = 0
    jobs_failed = 0
    for (organisation_id,) in db.query(Organisation.id).all():
        TenantScopedSession(db, organisation_id)
        pending_ids = [
            job_id
            for (job_id,) in db.query(ReportJob.id)
            .filter(ReportJob.organisation_id == organisation_id, ReportJob.status == ReportJobStatus.PENDING)
            .order_by(ReportJob.requested_at)
            .limit(limit)
            .all()
        ]
        for job_id in pending_ids:
            job = process_report_job(db, uuid.UUID(str(job_id)))
            if job is None:
                continue
            jobs_processed += 1
            if job.status == ReportJobStatus.FAILED:
                jobs_failed += 1

    return ReportGenerationResult(jobs_processed=jobs_processed, jobs_failed=jobs_failed)
