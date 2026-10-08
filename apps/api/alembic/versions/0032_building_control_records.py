"""Building Control & regulatory mapping — spec §30, architecture
03-development-domain.md §5's `building_control_records`. Development/
Building already capture a bare building_control_reference/bsr_reference
pair (as plain ExternalReference values, untouched by this migration);
this table is additive — the actual application lifecycle (body,
application/approval dates, status, conditions) spec §30 also asks for,
which those two bare strings never captured.

Revision ID: 0032_building_control_records
Revises: 0031_list_endpoint_sort_indexes
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_building_control_records"
down_revision: Union[str, None] = "0031_list_endpoint_sort_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table_name} ON {table_name}
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def _provenance_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.execute("ALTER TYPE externalreferencetype ADD VALUE IF NOT EXISTS 'BUILDING_CONTROL_COMPLETION_REFERENCE'")

    op.create_table(
        "building_control_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("body", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("SUBMITTED", "APPROVED", "CONDITIONAL", "COMPLETED", "REJECTED", name="buildingcontrolstatus"),
            nullable=False,
            server_default="SUBMITTED",
        ),
        sa.Column("application_date", sa.Date, nullable=True),
        sa.Column("approval_date", sa.Date, nullable=True),
        sa.Column("conditions", sa.Text, nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_building_control_records_organisation_id", "building_control_records", ["organisation_id"])
    op.create_index("ix_building_control_records_development_id", "building_control_records", ["development_id"])
    op.create_index("ix_building_control_records_building_id", "building_control_records", ["building_id"])
    _tenant_rls("building_control_records")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_building_control_records ON building_control_records")
    op.drop_table("building_control_records")
    op.execute("DROP TYPE IF EXISTS buildingcontrolstatus")
