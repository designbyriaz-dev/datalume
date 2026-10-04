"""Spec §72 load test, part 2 — follow-up to scripts/load_test.py,
measuring the remaining Python-aggregation endpoints STATUS.md flagged
but didn't measure in that first pass: get_defects_intelligence and
get_board_assurance_report.

Reuses the "Load Test Housing" organisation and the 20,000 properties
scripts/load_test.py already seeded — run that script first (or point
at a database where it has already run).

Board assurance (app/operations/compliance/assurance.py) calls
compliance_status() once per applicable (entity, requirement) pair,
and compliance_status() itself issues several queries per call
(status config, applicability, latest inspection, open actions) — an
O(properties x requirements) problem with a real constant-factor cost
per pair, not just one big table load like the others. Seeding that
shape at the full 20,000-property scale would mean hundreds of
thousands of individual ORM queries in this one script — instead this
measures the real per-pair cost at a smaller, still-real scale (2,000
properties, one requirement each = 2,000 pairs) and extrapolates
linearly, labelled clearly as extrapolated rather than measured.

Usage (from apps/api, venv active, DATABASE_URL pointed at the
already-load-tested Postgres):

    python ../../scripts/load_test_part2.py
"""

import os
import time

import psycopg

assert os.environ.get("DATABASE_URL", "").startswith("postgresql"), "DATABASE_URL must point at real Postgres"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

DEFECTS_PER_PROPERTY = 2
APPLICABILITY_SAMPLE_SIZE = 2_000

conn = psycopg.connect(dbname="datalume")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id FROM organisations WHERE name = 'Load Test Housing'")
row = cur.fetchone()
assert row is not None, "Run scripts/load_test.py first to seed 'Load Test Housing'"
org_id = str(row[0])
print(f"organisation_id = {org_id}")

cur.execute("SELECT count(*) FROM properties WHERE organisation_id = %s", (org_id,))
property_count = cur.fetchone()[0]
print(f"properties for org: {property_count:,}")

client.post("/api/v1/auth/login", json={"email": "admin@loadtest-housing.example", "password": "correct-horse-battery"})
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


print(f"\nSeeding {property_count * DEFECTS_PER_PROPERTY:,} defects...")
t0 = time.perf_counter()
cur.execute(
    """
    INSERT INTO defects (
        id, organisation_id, defect_reference, property_id, category,
        description, severity, reported_date, contractor, target_date,
        completion_date, status, warranty_related, source_type, created_at, updated_at
    )
    SELECT
        gen_random_uuid(),
        %(org_id)s,
        'DEF-' || lpad((row_number() OVER ())::text, 7, '0'),
        p.id,
        (ARRAY['Damp','Cracking','Leak','Electrical fault','Subsidence'])[1 + (def_num %% 5)],
        'Load-test defect ' || def_num || ' for ' || p.property_reference,
        (ARRAY['LOW','MEDIUM','HIGH','CRITICAL'])[1 + (def_num %% 4)]::defectseverity,
        (CURRENT_DATE - (def_num * 13 + 1) * INTERVAL '1 day')::date,
        (ARRAY['Acme Contractors','FixIt Ltd','BuildRight'])[1 + (def_num %% 3)],
        (CURRENT_DATE + (def_num %% 30) * INTERVAL '1 day')::date,
        CASE WHEN def_num %% 3 = 0 THEN (CURRENT_DATE - (def_num * 4) * INTERVAL '1 day')::date ELSE NULL END,
        (ARRAY['OPEN','ASSIGNED','IN_PROGRESS','COMPLETED','CLOSED'])[1 + (def_num %% 5)]::defectstatus,
        (def_num %% 5 = 0),
        'SYSTEM_GENERATED'::sourcetype,
        now(),
        now()
    FROM properties p
    CROSS JOIN generate_series(1, %(per_property)s) AS def_num
    WHERE p.organisation_id = %(org_id)s
    """,
    {"org_id": org_id, "per_property": DEFECTS_PER_PROPERTY},
)
print(f"  done in {time.perf_counter() - t0:.2f}s")

print("\n--- Python-aggregated endpoint ---")
timed("GET /api/v1/defects/intelligence", lambda: client.get("/api/v1/defects/intelligence", headers=headers))

print(f"\nSeeding compliance catalog and {APPLICABILITY_SAMPLE_SIZE:,} requirement-applicability rows...")
frameworks = client.get("/api/v1/compliance/frameworks", headers=headers)
assert frameworks.status_code == 200, frameworks.text[:300]

domains = client.get("/api/v1/compliance/domains", headers=headers).json()
gas_safety_domain_id = next(d["id"] for d in domains if d["code"] == "GAS_SAFETY")

requirement = client.post(
    "/api/v1/compliance/requirements",
    headers=headers,
    json={
        "domain_id": gas_safety_domain_id,
        "code": "LOAD_TEST_GAS_CERT",
        "title": "Load-test annual gas safety certificate",
        "cadence": "ANNUAL",
        "effective_date": "2020-01-01",
    },
).json()
requirement_id = requirement["id"]
print(f"  created org-scoped requirement_id = {requirement_id}")

cur.execute(
    """
    INSERT INTO requirement_applicability (
        id, organisation_id, requirement_id, entity_type, entity_id, applicable_from
    )
    SELECT
        gen_random_uuid(),
        %(org_id)s,
        %(requirement_id)s,
        'property',
        p.id::text,
        (CURRENT_DATE - INTERVAL '2 years')::date
    FROM properties p
    WHERE p.organisation_id = %(org_id)s
    LIMIT %(sample_size)s
    """,
    {"org_id": org_id, "requirement_id": requirement_id, "sample_size": APPLICABILITY_SAMPLE_SIZE},
)
print(f"  done")

cur.close()
conn.close()

print(f"\n--- N-queries-per-pair endpoint, measured at {APPLICABILITY_SAMPLE_SIZE:,} pairs (not the full {property_count:,}) ---")
best = timed(
    f"GET /api/v1/compliance/assurance-report (portfolio-wide, {APPLICABILITY_SAMPLE_SIZE:,} applicability pairs)",
    lambda: client.get("/api/v1/compliance/assurance-report", headers=headers),
    repeats=2,
)
projected = best * (property_count / APPLICABILITY_SAMPLE_SIZE)
print(
    f"  linear projection at {property_count:,} properties x 1 requirement each "
    f"({property_count:,} pairs): ~{projected:.1f}s (EXTRAPOLATED, not measured directly)"
)

print("\nDone.")
