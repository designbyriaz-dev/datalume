"""MFA backup/recovery codes — app/auth/models.py MfaBackupCode.

No tenant RLS here, same as `sessions`/`users`/`roles` in
0001_foundation.py's RLS_TABLES list: this is user-level data, not
organisation-scoped, so there is no organisation_id to scope by.

Revision ID: 0023_mfa_backup_codes
Revises: 0022_invitations
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_mfa_backup_codes"
down_revision: Union[str, None] = "0022_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("mfa_backup_codes")
