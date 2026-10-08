"""Load test for the data-health finding-persistence fix (STATUS.md's
"run_data_health_checks persists via a plain Python loop" gap, closed
in app/data_health/rules.py by replacing the per-row db.add() loop
with a single bulk INSERT).

Unlike scripts/load_test.py and its sequels, this one runs against
SQLite (same engine app/tests/conftest.py's `client` fixture uses),
not real Postgres — no Postgres instance is available in this
environment. That's a fair substitute here because the fix being
measured (one bulk INSERT vs N individual db.add() calls) is a
SQLAlchemy/ORM-layer cost, not a query-planner one, so it reproduces
on SQLite just as it would on Postgres; the already-fixed SQL
aggregation side of run_data_health_checks (STATUS.md's "~8x faster
(query)" entry) is Postgres-specific and is NOT re-measured here.

Two things are measured:

1. The specific fix in isolation: N findings persisted via the old
   per-row db.add() loop vs the new single bulk INSERT, same SQLite
   session, nothing else in the request involved.
2. The full GET /api/v1/data-health endpoint via TestClient, at the
   ticket's own two scales — a realistic 90%-coverage seed (20,000
   properties, 4,000 findings) and the extreme case it names explicitly
   (every property failing multiple checks, ~40,000 findings) — to
   confirm the endpoint itself got faster, not just the isolated insert.

Usage (from apps/api, venv active):

    python ../../scripts/load_test_data_health.py
"""

import os
import time
import uuid
from datetime import date

os.environ.setdefault("STRIPE_SECRET_KEY", "")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "")

from sqlalchemy import create_engine, insert  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.core.db as db_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.provenance import SourceType  # noqa: E402
from app.data_health.models import DataHealthFinding, FindingSeverity  # noqa: E402
from app.development.models import Property, PropertyStatus  # noqa: E402
from app.identifiers.models import ExternalReference, ExternalReferenceType  # noqa: E402
from app.operations.stock_condition.models import StockConditionSurvey  # noqa: E402

# Importing app.main registers every model module (organisations, auth,
# etc.) on Base.metadata — without it, create_all below can't resolve
# data_health_findings' FK to organisations.id.
import app.main  # noqa: E402,F401


def fresh_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def timed(label, fn, repeats=3):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    best = min(times)
    print(f"  {label}: best of {repeats} = {best * 1000:.1f}ms  (all: {[f'{t * 1000:.0f}ms' for t in times]})")
    return best


print("--- Part 1: finding persistence in isolation (old per-row db.add() loop vs new bulk INSERT) ---")

for finding_count in (4_000, 40_000):
    print(f"\n{finding_count:,} findings:")
    rows = [
        {
            "organisation_id": uuid.uuid4(),
            "check_code": "MISSING_UPRN",
            "severity": FindingSeverity.LOW,
            "affected_entity_type": "property",
            "affected_entity_id": str(uuid.uuid4()),
            "message": "Load-test finding.",
        }
        for _ in range(finding_count)
    ]

    def old_per_row_loop():
        db = fresh_session()
        try:
            for row in rows:
                db.add(DataHealthFinding(**row))
            db.flush()
        finally:
            db.close()

    def new_bulk_insert():
        db = fresh_session()
        try:
            db.execute(insert(DataHealthFinding), rows)
            db.flush()
        finally:
            db.close()

    before = timed("old: db.add() x N in a loop", old_per_row_loop)
    after = timed("new: single bulk INSERT", new_bulk_insert)
    print(f"  -> {before / after:.1f}x faster")


print("\n--- Part 2: full GET /api/v1/data-health endpoint (current, fixed code) ---")

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
db_module.SessionLocal = TestingSessionLocal

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[db_module.get_db] = override_get_db
client = TestClient(app)

signup = client.post(
    "/api/v1/auth/signup",
    json={
        "name": "Load Test Admin",
        "email": "admin@loadtest-data-health.example",
        "password": "correct-horse-battery",
        "organisation_name": "Load Test Data Health",
        "organisation_type": "HOUSING_ASSOCIATION",
        "goals": [],
    },
).json()
org_id = signup["organisation_id"]
org_uuid = uuid.UUID(org_id)
headers = {"X-Organisation-Id": org_id}

PROPERTY_COUNT = 20_000


def seed(missing_uprn_ids: set[int], missing_survey_ids: set[int]):
    """`missing_uprn_ids`/`missing_survey_ids` are property indices (not
    disjoint by construction — the extreme case below deliberately
    overlaps them, every property missing both). Every property has
    postcode and property_type set, so those two checks never fire
    here."""
    db = TestingSessionLocal()
    try:
        db.query(DataHealthFinding).delete()
        db.query(ExternalReference).delete()
        db.query(StockConditionSurvey).delete()
        db.query(Property).delete()
        db.commit()

        property_ids = [uuid.uuid4() for _ in range(PROPERTY_COUNT)]
        db.execute(
            insert(Property),
            [
                {
                    "id": pid,
                    "organisation_id": org_uuid,
                    "property_reference": f"PROP-{i:06d}",
                    "address": f"{i} Load Test Street",
                    "postcode": "TE1 1ST",
                    "property_type": "FLAT",
                    "status": PropertyStatus.OPERATIONAL,
                    "source_type": SourceType.SYSTEM_GENERATED,
                }
                for i, pid in enumerate(property_ids)
            ],
        )
        uprn_rows = [
            {
                "id": uuid.uuid4(),
                "organisation_id": org_uuid,
                "entity_type": "property",
                "entity_id": str(pid),
                "reference_type": ExternalReferenceType.UPRN,
                "value": f"UPRN-{i}",
                "source_type": SourceType.MANUAL,
            }
            for i, pid in enumerate(property_ids)
            if i not in missing_uprn_ids
        ]
        if uprn_rows:
            db.execute(insert(ExternalReference), uprn_rows)
        survey_rows = [
            {
                "id": uuid.uuid4(),
                "organisation_id": org_uuid,
                "property_id": pid,
                "survey_date": date(2026, 1, 1),
                "surveyor": "Load Test Surveyor",
                "source_type": SourceType.SYSTEM_GENERATED,
            }
            for i, pid in enumerate(property_ids)
            if i not in missing_survey_ids
        ]
        if survey_rows:
            db.execute(insert(StockConditionSurvey), survey_rows)
        db.commit()
    finally:
        db.close()


def get_data_health():
    resp = client.get("/api/v1/data-health", headers=headers)
    assert resp.status_code == 200, resp.text[:300]
    return resp.json()


print(f"\nSeeding {PROPERTY_COUNT:,} properties, 2,000 missing UPRN, 2,000 missing stock condition survey...")
seed(missing_uprn_ids=set(range(2_000)), missing_survey_ids=set(range(2_000, 4_000)))
body = get_data_health()
assert body["findings_total"] == 4_000, body["findings_total"]
timed("GET /api/v1/data-health (4,000 findings, realistic 90% coverage)", get_data_health)

print(f"\nSeeding {PROPERTY_COUNT:,} properties, ALL missing UPRN and stock condition survey (extreme case)...")
seed(missing_uprn_ids=set(range(PROPERTY_COUNT)), missing_survey_ids=set(range(PROPERTY_COUNT)))
body = get_data_health()
assert body["findings_total"] == 40_000, body["findings_total"]
timed("GET /api/v1/data-health (40,000 findings, extreme case)", get_data_health)

print("\nDone.")
