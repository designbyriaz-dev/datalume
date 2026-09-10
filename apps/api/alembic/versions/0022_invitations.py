"""Membership invitations — app/auth/models.py Invitation.

No tenant RLS on this table, deliberately: the accept endpoints
(app/organisations/router.py) look a row up by its own unguessable
token before the visitor has any organisation membership at all, so
there is no app.current_org_id to scope by yet at that point in the
flow. The authenticated invite/list/revoke endpoints filter by
organisation_id in application code instead (the same app-layer half
of the "two-layer" model every other table also gets, just without the
Postgres layer here) — the token itself, not RLS, is what authorizes
the public accept path, the same role the Stripe webhook signature
plays for that endpoint (see app/platform/router.py).

Revision ID: 0022_invitations
Revises: 0021_reports
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_invitations"
down_revision: Union[str, None] = "0021_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "REVOKED", "EXPIRED", name="invitationstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invitations_organisation_id", "invitations", ["organisation_id"])
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("invitations")
    op.execute("DROP TYPE IF EXISTS invitationstatus")
