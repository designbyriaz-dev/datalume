"""Specification register — architecture/03-development-domain.md §4.

Revision ID: 0009_specifications
Revises: 0008_components
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_specifications"
down_revision: Union[str, None] = "0008_components"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "specifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("lineage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specification_reference", sa.String(32), nullable=False),
        # Plain polymorphic reference (no FK), same pattern as
        # documents.related_entity_type/id — see app/development/models.py.
        sa.Column("related_entity_type", sa.String(64), nullable=False),
        sa.Column("related_entity_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("revision", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "SUPERSEDED", name="specificationstatus"),
            nullable=False,
        ),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("superseded_date", sa.Date, nullable=True),
        sa.Column("related_component_type", sa.String(128), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_specifications_organisation_id", "specifications", ["organisation_id"])
    op.create_index("ix_specifications_lineage_id", "specifications", ["lineage_id"])
    op.create_index(
        "ix_specifications_related_entity", "specifications", ["related_entity_type", "related_entity_id"]
    )

    op.execute("ALTER TABLE specifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE specifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_specifications ON specifications
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_specifications ON specifications")
    op.drop_table("specifications")
    op.execute("DROP TYPE IF EXISTS specificationstatus")
