"""Per-request structured logging — architecture/09-security-testing-ops.md
§3. `request_id`/`organisation_id`/`actor_user_id` are bound via
structlog's contextvars (not passed as kwargs to one log call), so
*every* log line emitted anywhere during the request — not just this
middleware's own summary line — carries them automatically, including
any logger.info/exception call a route or service function makes.
contextvars are per-asyncio-Task, and Starlette runs each request in
its own Task, so concurrent requests never bleed into each other's
bound fields.

`actor_user_id` is resolved the same way `get_current_user` (core/
tenancy.py) resolves it — a Redis lookup on the session cookie — but
read-only (no `.expire()` call): this is a best-effort log correlation
lookup, not the actual authentication check, and must not extend a
session's TTL just because a request happened to be logged. A request
with no cookie, an expired session, or a since-forged organisation_id
header still gets logged (with `actor_user_id`/`organisation_id` as
whatever partial information exists) — the real authorization decision
is still made by get_auth_context/require_permission, this middleware
only observes and logs.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.tenancy import hash_session_token, redis_client

logger = structlog.get_logger("datalume.request")


def _resolve_actor_user_id(request: Request) -> str | None:
    from app.core.config import get_settings

    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    try:
        return redis_client.get(f"session:{hash_session_token(token)}")
    except Exception:
        # Best-effort log correlation, not the real auth check (that's
        # get_current_user, which runs later in the same request and
        # will legitimately 401/500 on its own if Redis is actually
        # down). A logging-only lookup must never be why an otherwise
        # servable request fails — caught during Sprint 24's own
        # concurrency smoke-check, which crashed every single request
        # against a Redis-less test setup until this was added.
        logger.warning("request_logging.actor_lookup_failed")
        return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        organisation_id = request.headers.get("x-organisation-id")
        actor_user_id = _resolve_actor_user_id(request)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
        )

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request.failed", method=request.method, path=request.url.path)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
        )
        response.headers["X-Request-Id"] = request_id
        return response
