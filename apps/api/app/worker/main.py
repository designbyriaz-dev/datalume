"""Background worker entrypoint.

This is this codebase's first registered job: the Attention Engine's
nightly scan (architecture/06-intelligence-layer.md §3, Sprint 21 per
the roadmap). Data Health/Handover Readiness/Planned Investment/
compliance_status all stayed deliberately computed-at-read-time rather
than job-driven — every one of those sprints noted this process would
be where a real scheduler eventually lands. Attention Signals are the
one engine architecture explicitly specifies as job-driven ("so Home
and Alerts read pre-computed signals — never scanning the whole
dataset on page load"), so this is the first, not a pattern the others
are expected to retrofit onto.

No new scheduling dependency (no APScheduler/Celery) — a plain
UTC-hour check against a "did we already run today" guard, run once
per heartbeat tick, is enough for a single nightly job and keeps this
process's only dependency the same ones already in pyproject.toml.
`ATTENTION_SCAN_HOUR_UTC` (default 2am UTC, a quiet hour for a
UK-hours product) is the only tunable; there is no cron string to
parse because there is only one nightly job.

Sprint 23 (Reporting) adds this worker's second job, and its first
on-demand one: report generation (architecture §4's "background job...
never generated synchronously in the request/response cycle"). A report
job needs to complete in seconds for a user waiting on it, not by the
next 2am scan, so it's polled on every heartbeat tick rather than
gated by an hour check — the tick interval was shortened from 30s to
5s accordingly, still a plain DB poll, no new dependency.

`ReportJob.requested_by` is this worker's first foreign key to a table
(`users`) outside the job code's own transitive imports — SQLAlchemy
only resolves a string-based ForeignKey against classes actually
imported in the current process, so without `import app.main` below,
the first report job processed here crashed with
NoReferencedTableError the moment this worker ran as its own process
(app/tests/conftest.py's test client didn't catch this, since it
already imports app.main to build the FastAPI app). Importing app.main
registers every domain's models the same way it does for the API
process — cheaper than hand-listing every model module this job (or
the next one) happens to reference.
"""

import os
import time
from datetime import date, datetime, timezone

import structlog

import app.main  # noqa: F401  (registers every domain's models in this process)
from app.core.db import SessionLocal
from app.worker.jobs.attention_scan import run_attention_scan_for_all_organisations
from app.worker.jobs.report_generation import process_pending_report_jobs

logger = structlog.get_logger("datalume.worker")

ATTENTION_SCAN_HOUR_UTC = int(os.environ.get("ATTENTION_SCAN_HOUR_UTC", "2"))
WORKER_TICK_SECONDS = int(os.environ.get("WORKER_TICK_SECONDS", "5"))


def _run_attention_scan() -> None:
    db = SessionLocal()
    try:
        results = run_attention_scan_for_all_organisations(db)
        for organisation_id, result in results.items():
            logger.info(
                "attention_scan.completed",
                organisation_id=str(organisation_id),
                rules_evaluated=result.rules_evaluated,
                signals_created=result.signals_created,
                signals_refreshed=result.signals_refreshed,
            )
    finally:
        db.close()


def _run_report_generation() -> None:
    db = SessionLocal()
    try:
        result = process_pending_report_jobs(db)
        if result.jobs_processed:
            logger.info(
                "report_generation.tick",
                jobs_processed=result.jobs_processed,
                jobs_failed=result.jobs_failed,
            )
    finally:
        db.close()


def main() -> None:
    logger.info(
        "worker.started",
        jobs_registered=2,
        attention_scan_hour_utc=ATTENTION_SCAN_HOUR_UTC,
        worker_tick_seconds=WORKER_TICK_SECONDS,
    )
    last_scan_date: date | None = None
    while True:
        time.sleep(WORKER_TICK_SECONDS)

        try:
            _run_report_generation()
        except Exception:
            logger.exception("report_generation.failed")

        now = datetime.now(timezone.utc)
        if now.hour == ATTENTION_SCAN_HOUR_UTC and last_scan_date != now.date():
            logger.info("attention_scan.starting")
            try:
                _run_attention_scan()
            except Exception:
                logger.exception("attention_scan.failed")
            last_scan_date = now.date()
        else:
            logger.info("worker.heartbeat")


if __name__ == "__main__":
    main()
