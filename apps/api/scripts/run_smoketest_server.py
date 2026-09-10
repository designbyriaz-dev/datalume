"""Boots the API against a local SQLite file with an in-process fake
Redis — no Docker, no real Postgres/Redis needed. This is the same
pattern used throughout this build's own manual live verification
(see STATUS.md's sprint write-ups), promoted from a throwaway script
into a real, checked-in one so the Playwright E2E suite
(apps/web/e2e/) can start it automatically via playwright.config.ts's
`webServer`, and so anyone cloning this repo can click through the
real UI without installing Postgres/Redis first.

Row Level Security (architecture 01 §1) is Postgres-only and is NOT
exercised by this — see STATUS.md's "Not yet done" for that gap.
Tenant isolation at the *application* layer (query scoping + membership
checks) is real and does run here, the same as in
app/tests/conftest.py's fixture, which this mirrors.

Usage: python scripts/run_smoketest_server.py [--port 8000] [--db-path ./smoketest.db]
"""

import argparse
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--db-path", default="./smoketest.db")
parser.add_argument("--fresh", action="store_true", help="Drop and recreate all tables before starting")
args = parser.parse_args()

os.environ.setdefault("DATABASE_URL", f"sqlite:///{args.db_path}")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3100"]')

import uvicorn

from app.core.db import Base, engine
import app.main  # noqa: F401  (registers every model module before create_all)

if args.fresh:
    Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)


class FakeRedis:
    """Same in-process fake as app/tests/conftest.py's fixture — no
    real Redis needed for sessions in this smoketest mode."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def expire(self, key, ttl):
        pass

    def delete(self, key):
        self.store.pop(key, None)


fake_redis = FakeRedis()
import app.auth.router as auth_router_module
import app.core.request_logging as request_logging_module
import app.core.tenancy as tenancy_module

tenancy_module.redis_client = fake_redis
auth_router_module.redis_client = fake_redis
request_logging_module.redis_client = fake_redis

if __name__ == "__main__":
    print(f"Smoketest API on http://localhost:{args.port} (db: {args.db_path})", file=sys.stderr)
    uvicorn.run(app.main.app, host="0.0.0.0", port=args.port)
