"""Attention Engine duplicate-signal race — app/attention/models.py
AttentionSignal.__table_args__.

Two concurrent scans for the same organisation (the nightly job racing
a manual "run scan now" trigger, or two overlapping manual triggers)
could both pass upsert_signal's check-then-write and both insert a row
for the same (rule, entity), before this fix. A partial unique index —
live (OPEN/ACKNOWLEDGED) rows only, since unlimited RESOLVED/DISMISSED
history for the same (org, rule, entity) is legitimate — turns the
loser's insert into a clean IntegrityError, recovered in
app/attention/service.py the same way app/identifiers/service.py
already recovers the Reference Engine's analogous bootstrap race.

Revision ID: 0024_attention_signal_race
Revises: 0023_mfa_backup_codes
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_attention_signal_race"
down_revision: Union[str, None] = "0023_mfa_backup_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_attention_signal_live_per_entity",
        "attention_signals",
        ["organisation_id", "rule_id", "entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'ACKNOWLEDGED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_attention_signal_live_per_entity", table_name="attention_signals")
