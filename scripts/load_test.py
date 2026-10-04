"""Spec §72 load test — seeds one real organisation with a realistic
large volume of properties and repairs, directly via SQL (fast,
bypasses RLS by connecting as the Postgres superuser — a volume-
generation shortcut, not a code path under test; insert-path
correctness is already covered by the rest of the test suite), then
measures real endpoint latency through the actual FastAPI app against
that volume. Results of the run this script was written for are
written up in STATUS.md, not repeated here.

Not a pytest test — a one-off measurement script for whoever next
needs to re-check or extend this. Destructive to run twice against the
same org (re-running re-signs-up "Load Test Housing" and fails on the
duplicate email) — drop/recreate the database first if re-seeding.

Usage (from apps/api, with the venv active, DATABASE_URL pointed at a
real, migrated Postgres, and the connecting OS user a Postgres
superuser so the bulk INSERTs below bypass RLS):

    python ../../scripts/load_test.py
"""

import os
import time

import psycopg

assert os.environ.get("DATABASE_URL", "").startswith("postgresql"), "DATABASE_URL must point at real Postgres"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

PROPERTY_COUNT = 20_000
REPAIRS_PER_PROPERTY = 10

print("Signing up load-test organisation...")
signup = client.post(
    "/api/v1/auth/signup",
    json={
        "name": "Load Test Admin",
        "email": "admin@loadtest-housing.example",
        "password": "correct-horse-battery",
        "organisation_name": "Load Test Housing",
        "organisation_type": "HOUSING_ASSOCIATION",
        "goals": [],
    },
).json()
org_id = signup["organisation_id"]
print(f"  organisation_id = {org_id}")

# Superuser connection (OS-user peer auth over the local Unix socket,
# same as a bare `psql -d datalume`) — bypasses RLS entirely, used only
# for bulk seeding of leaf data. Real inserts in the app always go
# through the RLS-enforcing `datalume` role; this is purely a
# volume-generation shortcut, not a code path under test.
conn = psycopg.connect(dbname="datalume")
conn.autocommit = True
cur = conn.cursor()

print(f"Seeding {PROPERTY_COUNT:,} properties...")
t0 = time.perf_counter()
cur.execute(
    """
    INSERT INTO properties (
        id, organisation_id, property_reference, address, postcode,
        property_type, status, source_type, created_at, updated_at
    )
    SELECT
        gen_random_uuid(),
        %(org_id)s,
        'PROP-' || lpad(gs::text, 6, '0'),
        gs || ' Test Street',
        'TE' || (1 + gs %% 9) || ' ' || (1 + gs %% 9) || 'ST',
        'FLAT',
        (ARRAY['OPERATIONAL','OCCUPIED','VOID','UNDER_CONSTRUCTION'])[1 + (gs %% 4)]::propertystatus,
        'SYSTEM_GENERATED'::sourcetype,
        now(),
        now()
    FROM generate_series(1, %(count)s) gs
    """,
    {"org_id": org_id, "count": PROPERTY_COUNT},
)
print(f"  done in {time.perf_counter() - t0:.2f}s")

print(f"Seeding {PROPERTY_COUNT * REPAIRS_PER_PROPERTY:,} repairs...")
t0 = time.perf_counter()
cur.execute(
    """
    INSERT INTO repairs (
        id, organisation_id, repair_reference, property_id, category,
        description, priority, is_emergency, reported_date, contractor,
        completed_date, cost_pence, status, source_type, created_at, updated_at
    )
    SELECT
        gen_random_uuid(),
        %(org_id)s,
        'REP-' || lpad((row_number() OVER ())::text, 7, '0'),
        p.id,
        (ARRAY['Heating','Plumbing','Electrical','Roofing','Windows'])[1 + (rep_num %% 5)],
        'Load-test repair ' || rep_num || ' for ' || p.property_reference,
        (ARRAY['EMERGENCY','URGENT','ROUTINE','PLANNED'])[1 + (rep_num %% 4)]::repairpriority,
        (rep_num %% 4 = 0),
        (CURRENT_DATE - (rep_num * 11 + 1) * INTERVAL '1 day')::date,
        (ARRAY['Acme Contractors','FixIt Ltd','BuildRight'])[1 + (rep_num %% 3)],
        CASE WHEN rep_num %% 3 = 0 THEN (CURRENT_DATE - (rep_num * 5) * INTERVAL '1 day')::date ELSE NULL END,
        5000 + (rep_num %% 50) * 137,
        (ARRAY['REPORTED','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED'])[1 + (rep_num %% 5)]::repairstatus,
        'SYSTEM_GENERATED'::sourcetype,
        now(),
        now()
    FROM properties p
    CROSS JOIN generate_series(1, %(per_property)s) AS rep_num
    WHERE p.organisation_id = %(org_id)s
    """,
    {"org_id": org_id, "per_property": REPAIRS_PER_PROPERTY},
)
print(f"  done in {time.perf_counter() - t0:.2f}s")

cur.execute("SELECT count(*) FROM properties WHERE organisation_id = %s", (org_id,))
print(f"  properties for org: {cur.fetchone()[0]:,}")
cur.execute("SELECT count(*) FROM repairs WHERE organisation_id = %s", (org_id,))
print(f"  repairs for org: {cur.fetchone()[0]:,}")

cur.close()
conn.close()

headers = {"X-Organisation-Id": org_id}


def timed(label, fn, repeats=3):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        resp = fn()
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        assert resp.status_code == 200, f"{label} failed: {resp.status_code} {resp.text[:300]}"
    best = min(times)
    print(f"  {label}: best of {repeats} = {best * 1000:.1f}ms  (all: {[f'{t*1000:.0f}ms' for t in times]})")
    return best


print("\n--- Paginated list endpoints (should stay fast regardless of volume) ---")
timed("GET /api/v1/properties (limit=100, default)", lambda: client.get("/api/v1/properties", headers=headers))
timed("GET /api/v1/properties?limit=500", lambda: client.get("/api/v1/properties?limit=500", headers=headers))
timed("GET /api/v1/properties?offset=19000 (deep page)", lambda: client.get("/api/v1/properties?offset=19000", headers=headers))
timed("GET /api/v1/repairs (limit=100, default)", lambda: client.get("/api/v1/repairs", headers=headers))
timed("GET /api/v1/repairs?limit=500", lambda: client.get("/api/v1/repairs?limit=500", headers=headers))
timed("GET /api/v1/repairs?offset=199000 (deep page)", lambda: client.get("/api/v1/repairs?offset=199000", headers=headers))

print("\n--- SQL-aggregated endpoints (fixed this session) ---")
timed("GET /api/v1/portfolio/summary", lambda: client.get("/api/v1/portfolio/summary", headers=headers))

print("\n--- Python-aggregated endpoints (flagged, not yet rewritten) ---")
timed("GET /api/v1/repairs/intelligence", lambda: client.get("/api/v1/repairs/intelligence", headers=headers), repeats=3)

print("\nDone.")
