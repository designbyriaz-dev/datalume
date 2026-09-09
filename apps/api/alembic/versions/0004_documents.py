"""Documents: versioned document/evidence storage — architecture/02-data-platform.md §4.

Also replaces datasets.source_file_storage_key (Sprint 3, a bare key)
with a proper FK to documents.id now that the Document model exists.

Revision ID: 0004_documents
Revises: 0003_ingestion
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_documents"
down_revision: Union[str, None] = "0003_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("lineage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_reference", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("revision", sa.String(32), nullable=False, server_default="A"),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "SUPERSEDED", "ARCHIVED", name="documentstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("superseded_by_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("related_entity_type", sa.String(64), nullable=True),
        sa.Column("related_entity_id", sa.String(64), nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
    )
    op.create_index("ix_documents_organisation_id", "documents", ["organisation_id"])
    op.create_index("ix_documents_lineage_id", "documents", ["lineage_id"])
    op.create_index(
        "ix_documents_related_entity", "documents", ["related_entity_type", "related_entity_id"]
    )

    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_documents ON documents
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )

    op.drop_column("datasets", "source_file_storage_key")
    op.add_column(
        "datasets",
        sa.Column("source_file_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("datasets", "source_file_document_id")
    op.add_column("datasets", sa.Column("source_file_storage_key", sa.String(255), nullable=True))

    op.execute("DROP POLICY IF EXISTS tenant_isolation_documents ON documents")
    op.drop_table("documents")
    op.execute("DROP TYPE IF EXISTS documentstatus")
