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
parse because there is only one job.
"""

import os
import time
from datetime import date, datetime, timezone

import structlog

from app.core.db import SessionLocal
from app.worker.jobs.attention_scan import run_attention_scan_for_all_organisations

logger = structlog.get_logger("datalume.worker")

ATTENTION_SCAN_HOUR_UTC = int(os.environ.get("ATTENTION_SCAN_HOUR_UTC", "2"))


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


def main() -> None:
    logger.info("worker.started", jobs_registered=1, attention_scan_hour_utc=ATTENTION_SCAN_HOUR_UTC)
    last_scan_date: date | None = None
    while True:
        time.sleep(30)
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
