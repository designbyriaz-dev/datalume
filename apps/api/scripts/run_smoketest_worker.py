"""Runs the real worker loop (app/worker/main.py) against the same
SQLite + fake-Redis smoketest setup as run_smoketest_server.py — so
report generation (Sprint 23) actually completes during E2E runs
instead of report jobs sitting PENDING forever. Must be run with the
same --db-path as the API process; DATABASE_URL is the only thing they
share (there's no other IPC between them, same as production).

Usage: python scripts/run_smoketest_worker.py --db-path ./smoketest.db
"""

import argparse
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--db-path", default="./smoketest.db")
args = parser.parse_args()

os.environ.setdefault("DATABASE_URL", f"sqlite:///{args.db_path}")
# Nightly attention scan never fires in a short-lived E2E run — fine,
# nothing here currently exercises it through the UI (no scan-trigger
# button exists; see STATUS.md). Report generation polls every tick
# regardless of hour, which is what E2E actually needs.

import app.main  # noqa: F401  (registers every domain's models — see worker/main.py's own docstring for why)


class FakeRedis:
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

from app.worker.main import main

if __name__ == "__main__":
    print(f"Smoketest worker on db: {args.db_path}", file=sys.stderr)
    main()
