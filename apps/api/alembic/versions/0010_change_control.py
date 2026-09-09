"""Change Control register — architecture/03-development-domain.md §7.

Revision ID: 0010_change_control
Revises: 0009_specifications
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_change_control"
down_revision: Union[str, None] = "0009_specifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New ExternalReferenceType member for change_control.approve's
    # optional external_approval_reference — same "route official
    # identifiers through ExternalReference, never a plain column"
    # constraint from Sprint 7 (see identifiers/models.py). Adding an
    # enum value cannot run inside the same transaction as code that
    # uses it, but that's not a concern here — this migration only adds
    # the value, nothing in it depends on the value existing yet.
    op.execute("ALTER TYPE externalreferencetype ADD VALUE IF NOT EXISTS 'EXTERNAL_APPROVAL_REFERENCE'")

    op.create_table(
        "change_controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("change_reference", sa.String(32), nullable=False),
        sa.Column("specification_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("specifications.id"), nullable=False),
        # Copied from the target specification at submission time — see
        # app/development/models.py's ChangeControl docstring for why
        # this isn't four separate nullable FK columns instead.
        sa.Column("related_entity_type", sa.String(64), nullable=False),
        sa.Column("related_entity_id", sa.String(64), nullable=False),
        sa.Column("previous_value", sa.JSON, nullable=False),
        sa.Column("proposed_value", sa.JSON, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("impact_description", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PROPOSED", "UNDER_REVIEW", "APPROVED", "REJECTED", "IMPLEMENTED", "CANCELLED",
                name="changecontrolstatus",
            ),
            nullable=False,
        ),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_date", sa.Date, nullable=True),
        sa.Column(
            "implemented_specification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("specifications.id"),
            nullable=True,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "MANUAL", "FILE_UPLOAD", "API", "SCHEDULED_IMPORT", "INTEGRATION", "SYSTEM_GENERATED",
                name="sourcetype",
            ),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(128), nullable=True),
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("original_reference", sa.String(255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_change_controls_organisation_id", "change_controls", ["organisation_id"])
    op.create_index("ix_change_controls_specification_id", "change_controls", ["specification_id"])
    op.create_index(
        "ix_change_controls_related_entity", "change_controls", ["related_entity_type", "related_entity_id"]
    )

    op.execute("ALTER TABLE change_controls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE change_controls FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_change_controls ON change_controls
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_change_controls ON change_controls")
    op.drop_table("change_controls")
    op.execute("DROP TYPE IF EXISTS changecontrolstatus")
    # Postgres cannot drop a single enum value without recreating the
    # type; EXTERNAL_APPROVAL_REFERENCE is left in externalreferencetype
    # on downgrade, same practical limitation as every other additive
    # enum value in this codebase's migration history.
