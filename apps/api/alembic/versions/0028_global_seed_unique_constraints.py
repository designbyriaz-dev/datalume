"""Add the unique constraints the global lazy-seeded catalogs
(component_types, compliance_frameworks, compliance_domains) were
always missing — found by a genuine concurrency test
(app/tests/test_rls_postgres.py's test_concurrent_requests_from_
different_organisations_never_cross_contaminate), which hit a real
UniqueViolation race on plans/roles (both already protected by a
unique constraint, just not race-safe code) and, checking every other
lazy "get or create a global row" function in the codebase for the
same shape, found these three tables had no unique constraint to even
catch the race — two concurrent first-ever callers wouldn't error,
they'd silently create duplicate rows.

Partial indexes (WHERE organisation_id IS NULL) rather than a plain
column-level unique constraint: the global seeded catalog needs unique
codes/names among itself, but a per-organisation custom addition
(component_types' own "org-extensible taxonomy" design, spec §22)
should stay free to reuse a code/name another org already used, or
that the global catalog itself uses — this only constrains the NULL-
organisation_id rows against each other.

Revision ID: 0028_global_seed_unique_constraints
Revises: 0027_memberships_own_rows_visible
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028_global_seed_unique_constraints"
down_revision: Union[str, None] = "0027_memberships_own_rows_visible"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX ux_component_types_global_code ON component_types (code) WHERE organisation_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_compliance_frameworks_global_name ON compliance_frameworks (name) WHERE organisation_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_compliance_domains_global_framework_code "
        "ON compliance_domains (framework_id, code) WHERE organisation_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_compliance_domains_global_framework_code")
    op.execute("DROP INDEX IF EXISTS ux_compliance_frameworks_global_name")
    op.execute("DROP INDEX IF EXISTS ux_component_types_global_code")
