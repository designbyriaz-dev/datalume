"""Spec §72 load test, part 3 — follow-up to scripts/load_test.py and
load_test_part2.py, measuring the one remaining known N+1 flagged but
left unfixed in STATUS.md: commercial/arrears.py's `collection_rate`
and `arrears_for_lease`, which used to call `matched_amount_for_
obligation` (its own query) once per rent obligation in a loop.

Documented as a narrower, bounded-N case than the board assurance
report (bounded by one lease, or by one date period, not an unbounded
org-wide scan) — but still a real, easy, safe-to-fix N+1, now fixed via
`matched_amounts_for_obligations` (app/commercial/service.py), a single
bulk query. This script measures `collection_rate` (the one of the two
where N can plausibly be large — a whole organisation's obligations
due in one period, not just one lease's) at a real volume.

Reuses the "Load Test Housing" organisation scripts/load_test.py
already seeded (needs its 20,000 properties for lease property_ids)
— run that script first.

Usage (from apps/api, venv active, DATABASE_URL pointed at the
already-load-tested Postgres):

    python ../../scripts/load_test_part3.py
"""

import os
import time

import psycopg

assert os.environ.get("DATABASE_URL", "").startswith("postgresql"), "DATABASE_URL must point at real Postgres"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

LEASE_COUNT = 5_000

conn = psycopg.connect(dbname="datalume")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id FROM organisations WHERE name = 'Load Test Housing'")
row = cur.fetchone()
assert row is not None, "Run scripts/load_test.py first to seed 'Load Test Housing'"
org_id = str(row[0])
print(f"organisation_id = {org_id}")

client.post("/api/v1/auth/login", json={"email": "admin@loadtest-housing.example", "password": "correct-horse-battery"})
headers = {"X-Organisation-Id": org_id}

print(f"\nSeeding {LEASE_COUNT:,} tenants, leases, and ~{LEASE_COUNT * 3:,} rent obligations/payment allocations...")
t0 = time.perf_counter()

cur.execute(
    """
    INSERT INTO tenants (id, organisation_id, name, contact_details, source_type, created_at, updated_at)
    SELECT gen_random_uuid(), %(org_id)s, 'Load-test tenant ' || gs, '{}'::jsonb, 'SYSTEM_GENERATED'::sourcetype, now(), now()
    FROM generate_series(1, %(count)s) gs
    """,
    {"org_id": org_id, "count": LEASE_COUNT},
)

cur.execute(
    """
    WITH numbered_properties AS (
        SELECT id, row_number() OVER (ORDER BY id) AS rn
        FROM properties WHERE organisation_id = %(org_id)s LIMIT %(count)s
    ),
    numbered_tenants AS (
        SELECT id, row_number() OVER (ORDER BY id) AS rn
        FROM tenants WHERE organisation_id = %(org_id)s LIMIT %(count)s
    )
    INSERT INTO leases (
        id, organisation_id, property_id, tenant_id, lease_reference, lease_start, lease_expiry,
        contractual_rent_pence, rent_frequency, occupancy_status, lease_status, source_type, created_at, updated_at
    )
    SELECT
        gen_random_uuid(), %(org_id)s, p.id, t.id,
        'LEASE-' || lpad(p.rn::text, 6, '0'),
        (CURRENT_DATE - INTERVAL '2 years')::date,
        (CURRENT_DATE + INTERVAL '1 year')::date,
        80000 + (p.rn %% 50) * 1000,
        'MONTHLY'::rentfrequency,
        'OCCUPIED'::occupancystatus,
        'ACTIVE'::leasestatus,
        'SYSTEM_GENERATED'::sourcetype,
        now(), now()
    FROM numbered_properties p JOIN numbered_tenants t ON t.rn = p.rn
    """,
    {"org_id": org_id, "count": LEASE_COUNT},
)

# Three monthly obligations each, all with a due_date inside the same
# quarter — the date window collection_rate's own query filters on.
cur.execute(
    """
    INSERT INTO rent_obligations (
        id, organisation_id, lease_id, obligation_type, due_date, period_start, period_end,
        amount_due_pence, currency, status, source_type, created_at, updated_at
    )
    SELECT
        gen_random_uuid(), %(org_id)s, l.id, 'RENT'::obligationtype,
        (DATE '2026-01-01' + (month_num - 1) * INTERVAL '1 month')::date,
        (DATE '2026-01-01' + (month_num - 1) * INTERVAL '1 month')::date,
        (DATE '2026-01-01' + month_num * INTERVAL '1 month' - INTERVAL '1 day')::date,
        l.contractual_rent_pence,
        'GBP',
        'ACTIVE'::rentobligationstatus,
        'SYSTEM_GENERATED'::sourcetype,
        now(), now()
    FROM leases l
    CROSS JOIN generate_series(1, 3) AS month_num
    WHERE l.organisation_id = %(org_id)s AND l.lease_reference LIKE 'LEASE-%%'
    """,
    {"org_id": org_id},
)

# One payment + one MATCHED allocation per obligation, covering ~70% of
# the amount due (a realistic partial-collection scenario) so
# collection_rate has real, varied numbers to sum rather than either
# "fully paid" or "fully unpaid" for everything.
cur.execute(
    """
    WITH obligations AS (
        SELECT ro.id AS obligation_id, ro.lease_id, ro.amount_due_pence, ro.due_date,
               row_number() OVER () AS rn
        FROM rent_obligations ro
        JOIN leases l ON l.id = ro.lease_id
        WHERE ro.organisation_id = %(org_id)s AND l.lease_reference LIKE 'LEASE-%%'
    ),
    inserted_payments AS (
        INSERT INTO payment_transactions (
            id, organisation_id, lease_id, amount_pence, currency, received_date, source_type, created_at, updated_at
        )
        SELECT gen_random_uuid(), %(org_id)s, lease_id, (amount_due_pence * 0.7)::int, 'GBP', due_date,
               'SYSTEM_GENERATED'::sourcetype, now(), now()
        FROM obligations
        RETURNING id, lease_id, amount_pence
    ),
    numbered_payments AS (
        SELECT id, lease_id, amount_pence, row_number() OVER () AS rn FROM inserted_payments
    )
    INSERT INTO payment_allocations (
        id, organisation_id, payment_transaction_id, rent_obligation_id, amount_allocated_pence,
        allocation_status, source_type
    )
    SELECT gen_random_uuid(), %(org_id)s, np.id, o.obligation_id, np.amount_pence,
           'MATCHED'::allocationstatus, 'SYSTEM_GENERATED'::sourcetype
    FROM numbered_payments np JOIN obligations o ON o.rn = np.rn
    """,
    {"org_id": org_id},
)
print(f"  done in {time.perf_counter() - t0:.2f}s")

cur.execute("SELECT count(*) FROM rent_obligations ro JOIN leases l ON l.id = ro.lease_id WHERE ro.organisation_id = %s", (org_id,))
obligation_count = cur.fetchone()[0]
print(f"  rent obligations for org: {obligation_count:,}")
cur.close()
conn.close()


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


print(f"\n--- GET /api/v1/collection-rate over the full Q1 2026 window ({obligation_count:,} obligations) ---")
timed(
    "GET /api/v1/collection-rate?period_start=2026-01-01&period_end=2026-03-31",
    lambda: client.get("/api/v1/collection-rate?period_start=2026-01-01&period_end=2026-03-31", headers=headers),
)

print("\nDone.")
