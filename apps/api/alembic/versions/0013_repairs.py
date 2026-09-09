"""Repairs and repair rule config — architecture/04-operations-domain.md §1-2.

Revision ID: 0013_repairs
Revises: 0012_handover
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_repairs"
down_revision: Union[str, None] = "0012_handover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("repair_reference", sa.String(32), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=True),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "priority",
            sa.Enum("EMERGENCY", "URGENT", "ROUTINE", "PLANNED", name="repairpriority"),
            nullable=False,
        ),
        sa.Column("is_emergency", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reported_date", sa.Date, nullable=False),
        sa.Column("contractor", sa.String(255), nullable=True),
        sa.Column("completed_date", sa.Date, nullable=True),
        sa.Column("cost_pence", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Enum("REPORTED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED", name="repairstatus"),
            nullable=False,
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
    op.create_index("ix_repairs_organisation_id", "repairs", ["organisation_id"])
    op.create_index("ix_repairs_property_id", "repairs", ["property_id"])
    op.create_index("ix_repairs_component_id", "repairs", ["component_id"])

    op.execute("ALTER TABLE repairs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE repairs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_repairs ON repairs
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )

    op.create_table(
        "repair_rule_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("window_months", sa.Integer, nullable=True),
        sa.Column("threshold", sa.Integer, nullable=True),
        sa.Column("threshold_ratio", sa.Float, nullable=True),
        sa.Column("min_installed_base", sa.Integer, nullable=True),
        sa.UniqueConstraint("organisation_id", "rule_code", name="uq_repair_rule_config_org_rule"),
    )
    op.create_index("ix_repair_rule_configs_organisation_id", "repair_rule_configs", ["organisation_id"])

    op.execute("ALTER TABLE repair_rule_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE repair_rule_configs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_repair_rule_configs ON repair_rule_configs
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_repair_rule_configs ON repair_rule_configs")
    op.drop_table("repair_rule_configs")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_repairs ON repairs")
    op.drop_table("repairs")
    op.execute("DROP TYPE IF EXISTS repairstatus")
    op.execute("DROP TYPE IF EXISTS repairpriority")
