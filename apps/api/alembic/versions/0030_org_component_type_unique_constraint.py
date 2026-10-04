"""Add a (organisation_id, code) unique constraint on component_types,
closing the exact-duplicate half of the one get_or_create race
STATUS.md left deliberately open after migrations 0028/0029:
get_or_create_org_component_type (app/development/component_types.py).

A plain UNIQUE(organisation_id, code) — not a partial index like
0028's global-catalog one — because SQL's NULL-is-never-equal-to-NULL
semantics mean this naturally only ever constrains the non-NULL-
organisation_id (per-org custom) rows against each other; it coexists
with 0028's own partial index (unique on code alone, WHERE
organisation_id IS NULL) without conflict, since the two protect
disjoint row subsets of the same table.

This closes the race where two concurrent CSV import rows for the same
org reference the exact same new, previously-unseen type name (code is
a deterministic function of name, so two calls with the same name
produce the same code and would now collide for real). It does NOT
close the narrower singular/plural-variant case (two concurrent
imports of e.g. "Boiler" and "Boilers" for the same org, which the
function's own fuzzy find_component_type_by_name treats as equivalent
but which derive genuinely different codes, "BOILER" vs "BOILERS", so
a database constraint can't catch it) — documented honestly in
app/development/component_types.py's own comment and in STATUS.md
rather than silently assumed fixed.

Revision ID: 0030_org_component_type_unique_constraint
Revises: 0029_per_org_config_unique_constraints
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_org_component_type_unique_constraint"
down_revision: Union[str, None] = "0029_per_org_config_unique_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("ux_component_types_org_code", "component_types", ["organisation_id", "code"])


def downgrade() -> None:
    op.drop_constraint("ux_component_types_org_code", "component_types", type_="unique")
