"""Ingestion: datasets, import_jobs, import_rows, mapping_templates —
architecture/02-data-platform.md §2.

Revision ID: 0003_ingestion
Revises: 0002_billing
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ingestion"
down_revision: Union[str, None] = "0002_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["datasets", "import_jobs", "import_rows", "mapping_templates"]


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dataset_type", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("UPLOADED", "VALIDATED", "MAPPED", "IMPORTED", "FAILED", name="datasetstatus"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source_file_storage_key", sa.String(255), nullable=True),
    )
    op.create_index("ix_datasets_organisation_id", "datasets", ["organisation_id"])

    op.create_table(
        "import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING", "AWAITING_MAPPING", "MAPPED", "IMPORTING", "COMPLETED", "FAILED",
                name="importjobstatus",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.String(1024), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_import_jobs_organisation_id", "import_jobs", ["organisation_id"])
    op.create_index("ix_import_jobs_dataset_id", "import_jobs", ["dataset_id"])

    op.create_table(
        "import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_jobs.id"), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "VALID", "INVALID", "IMPORTED", "SKIPPED", name="importrowstatus"),
            nullable=False,
        ),
        sa.Column("errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("mapped_entity_type", sa.String(64), nullable=True),
        sa.Column("mapped_entity_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_import_rows_organisation_id", "import_rows", ["organisation_id"])
    op.create_index("ix_import_rows_import_job_id", "import_rows", ["import_job_id"])

    op.create_table(
        "mapping_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("dataset_type", sa.String(64), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mapping_templates_organisation_id", "mapping_templates", ["organisation_id"])

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
                organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
            )
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("mapping_templates")
    op.drop_table("import_rows")
    op.drop_table("import_jobs")
    op.drop_table("datasets")
    op.execute("DROP TYPE IF EXISTS importrowstatus")
    op.execute("DROP TYPE IF EXISTS importjobstatus")
    op.execute("DROP TYPE IF EXISTS datasetstatus")
