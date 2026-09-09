"""Structured JSON logging — architecture/09-security-testing-ops.md §3:
"Structured JSON logging (structlog) with organisation_id, request_id,
actor_user_id on every log line." Until Sprint 24, only
app/worker/main.py used structlog, and with no `structlog.configure(...)`
call anywhere, it ran on structlog's own untuned defaults (a
human-readable console renderer, not JSON). `configure_structlog()` is
called once from app/main.py at import time; structlog configuration is
process-global, so the worker's existing logger picks this up too
without needing its own setup.
"""

import structlog


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=True,
    )
