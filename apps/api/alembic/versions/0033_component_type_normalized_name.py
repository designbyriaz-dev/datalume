"""Close the race migration 0030 deliberately left open:
get_or_create_org_component_type (app/development/component_types.py).

Two concurrent CSV import rows for the same org and names that
find_component_type_by_name's own singular/plural matching already
treats as equivalent (e.g. "Boiler" vs "Boilers") derive genuinely
different `code` values (BOILER vs BOILERS), so 0030's (organisation_id,
code) constraint never saw them as a collision — each could still create
its own row. normalized_name is the actual uniqueness key those two
calls share: a naive de-pluralised, lower-cased form, computed the same
way in Python (app/development/component_types.py's own
_normalize_name) and persisted here so the database can enforce it
directly instead of only checking it in application code a concurrent
transaction could race past.

Added nullable first since a real deployment could already have rows
(same three-step shape as 0026_rent_obligation_provenance.py): backfill
every existing row's normalized_name from its own name, enforce NOT
NULL, then add the constraint.

Revision ID: 0033_component_type_normalized_name
Revises: 0032_building_control_records
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_component_type_normalized_name"
down_revision: Union[str, None] = "0032_building_control_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("component_types", sa.Column("normalized_name", sa.String(128), nullable=True))
    # Same naive de-pluralisation as _singularish: lower-case, trimmed,
    # trailing "s" dropped unless the word ends "ss" (so "Boilers" ->
    # "boiler" but "Glass" stays "glass").
    op.execute(
        """
        UPDATE component_types
        SET normalized_name = (
            CASE
                WHEN lower(trim(name)) LIKE '%ss' THEN lower(trim(name))
                WHEN lower(trim(name)) LIKE '%s' THEN left(lower(trim(name)), length(lower(trim(name))) - 1)
                ELSE lower(trim(name))
            END
        )
        WHERE normalized_name IS NULL
        """
    )
    op.alter_column("component_types", "normalized_name", nullable=False)
    op.create_unique_constraint(
        "ux_component_types_org_normalized_name", "component_types", ["organisation_id", "normalized_name"]
    )


def downgrade() -> None:
    op.drop_constraint("ux_component_types_org_normalized_name", "component_types", type_="unique")
    op.drop_column("component_types", "normalized_name")
