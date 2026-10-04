"""Add the unique constraints seven per-organisation lazily-seeded
config/weight tables were always missing — the narrower, per-org
counterpart to migration 0028's global catalog fix (see STATUS.md:
found by the same audit, same reasoning, deliberately not rushed
through alongside 0028 since the race window here is two concurrent
requests for the *same org's* first-ever touch of one config, not
every org's first touch colliding with every other org's).

Each of these follows the exact same lazy "get or create, no race
protection" shape 0028 already fixed for the global catalogs: a plain
check-then-insert with no unique constraint underneath it, so two
concurrent first-ever callers for the same (org[, code]) wouldn't
error, they'd silently create a duplicate row. Two are genuinely
per-(org, code) — a weight/threshold row per rule the org can tune
independently; the "true singletons" (named in their own model
docstrings as exactly that) are per-org only.

Revision ID: 0029_per_org_config_unique_constraints
Revises: 0028_global_seed_unique_constraints
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029_per_org_config_unique_constraints"
down_revision: Union[str, None] = "0028_global_seed_unique_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, unique columns) — per-(org, code) first, true per-org singletons second.
PER_ORG_CODE_TABLES = [
    ("handover_readiness_check_weights", ["organisation_id", "check_code"]),
    ("planned_investment_weights", ["organisation_id", "factor_code"]),
    ("repair_rule_configs", ["organisation_id", "rule_code"]),
    ("hazard_rule_configs", ["organisation_id", "rule_code"]),
]
PER_ORG_SINGLETON_TABLES = [
    "planned_investment_configs",
    "compliance_status_configs",
    "payment_reconciliation_configs",
]


def upgrade() -> None:
    for table, columns in PER_ORG_CODE_TABLES:
        op.create_unique_constraint(f"ux_{table}_org_code", table, columns)
    for table in PER_ORG_SINGLETON_TABLES:
        op.create_unique_constraint(f"ux_{table}_org", table, ["organisation_id"])


def downgrade() -> None:
    for table, _columns in PER_ORG_CODE_TABLES:
        op.drop_constraint(f"ux_{table}_org_code", table, type_="unique")
    for table in PER_ORG_SINGLETON_TABLES:
        op.drop_constraint(f"ux_{table}_org", table, type_="unique")
