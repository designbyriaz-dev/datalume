"""Ingestion IMPORT step — architecture/02-data-platform.md §2 /
spec §72: "tens of thousands of properties" is a real performance
requirement the synchronous version couldn't meet (a large import
blocking the request that triggered it). Only IMPORT moves to the
worker; UPLOAD/VALIDATE/UNDERSTAND/MAP/REVIEW stay synchronous because
MAP+REVIEW's proposed mapping has to return to the browser immediately
for a human to review and edit before anything commits.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.models import ImportJob, ImportJobStatus
from app.ingestion.pipeline import process_import_job


@dataclass
class IngestionResult:
    jobs_processed: int
    jobs_failed: int


def process_pending_import_jobs(db: Session, *, limit: int = 20) -> IngestionResult:
    pending_ids = [
        job_id
        for (job_id,) in db.query(ImportJob.id)
        .filter(ImportJob.status == ImportJobStatus.IMPORTING)
        .order_by(ImportJob.started_at)
        .limit(limit)
        .all()
    ]

    jobs_processed = 0
    jobs_failed = 0
    for job_id in pending_ids:
        job = process_import_job(db, uuid.UUID(str(job_id)))
        if job is None:
            continue
        jobs_processed += 1
        if job.status == ImportJobStatus.FAILED:
            jobs_failed += 1

    return IngestionResult(jobs_processed=jobs_processed, jobs_failed=jobs_failed)
