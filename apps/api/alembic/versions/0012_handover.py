"""Handover Readiness weights and Handover records — architecture/03-development-domain.md §8-9.

Revision ID: 0012_handover
Revises: 0011_defects_warranties
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_handover"
down_revision: Union[str, None] = "0011_defects_warranties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "handover_readiness_check_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("check_code", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.UniqueConstraint("organisation_id", "check_code", name="uq_handover_weight_org_check"),
    )
    op.create_index(
        "ix_handover_readiness_check_weights_organisation_id", "handover_readiness_check_weights", ["organisation_id"]
    )
    op.execute("ALTER TABLE handover_readiness_check_weights ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE handover_readiness_check_weights FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_handover_readiness_check_weights ON handover_readiness_check_weights
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )

    op.create_table(
        "handover_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=False),
        sa.Column("readiness_score_pct", sa.Float, nullable=False),
        sa.Column("readiness_snapshot", sa.JSON, nullable=False),
        sa.Column("override_reason", sa.Text, nullable=True),
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
    op.create_index("ix_handover_records_organisation_id", "handover_records", ["organisation_id"])
    op.create_index("ix_handover_records_property_id", "handover_records", ["property_id"])
    op.create_index("ix_handover_records_development_id", "handover_records", ["development_id"])
    op.execute("ALTER TABLE handover_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE handover_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_handover_records ON handover_records
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_handover_records ON handover_records")
    op.drop_table("handover_records")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_handover_readiness_check_weights ON handover_readiness_check_weights")
    op.drop_table("handover_readiness_check_weights")
