"""Reporting & export — architecture/06-intelligence-layer.md §4.

Revision ID: 0021_reports
Revises: 0020_attention_engine
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_reports"
down_revision: Union[str, None] = "0020_attention_engine"
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


def upgrade() -> None:
    op.create_table(
        "report_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column(
            "report_type",
            sa.Enum(
                "DEVELOPMENT_SUMMARY",
                "HANDOVER_READINESS",
                "COMPLIANCE_EXECUTIVE_SUMMARY",
                "BOARD_ASSURANCE",
                "COMMERCIAL_PORTFOLIO",
                name="reporttype",
            ),
            nullable=False,
        ),
        sa.Column("format", sa.Enum("PDF", "XLSX", "CSV", name="reportformat"), nullable=False),
        sa.Column("filters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "READY", "FAILED", name="reportjobstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("storage_key", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
    )
    op.create_index("ix_report_jobs_organisation_id", "report_jobs", ["organisation_id"])
    op.create_index("ix_report_jobs_status", "report_jobs", ["status"])
    _tenant_rls("report_jobs")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_report_jobs ON report_jobs")
    op.drop_table("report_jobs")
    op.execute("DROP TYPE IF EXISTS reportjobstatus")
    op.execute("DROP TYPE IF EXISTS reportformat")
    op.execute("DROP TYPE IF EXISTS reporttype")
