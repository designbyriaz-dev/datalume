"""Defect & Warranty registers — architecture/03-development-domain.md §8.

Revision ID: 0011_defects_warranties
Revises: 0010_change_control
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_defects_warranties"
down_revision: Union[str, None] = "0010_change_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _enable_tenant_rls(table_name: str) -> None:
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
        "defects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("defect_reference", sa.String(32), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=True),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="defectseverity"), nullable=False),
        sa.Column("reported_date", sa.Date, nullable=False),
        sa.Column("contractor", sa.String(255), nullable=True),
        sa.Column("responsible_party", sa.String(255), nullable=True),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("completion_date", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN", "ASSIGNED", "IN_PROGRESS", "READY_FOR_INSPECTION", "COMPLETED", "REJECTED", "CLOSED",
                name="defectstatus",
            ),
            nullable=False,
        ),
        sa.Column("estimated_cost_pence", sa.Integer, nullable=True),
        sa.Column("actual_cost_pence", sa.Integer, nullable=True),
        sa.Column("warranty_related", sa.Boolean, nullable=False, server_default=sa.false()),
        *_provenance_columns(),
    )
    op.create_index("ix_defects_organisation_id", "defects", ["organisation_id"])
    op.create_index("ix_defects_development_id", "defects", ["development_id"])
    op.create_index("ix_defects_building_id", "defects", ["building_id"])
    op.create_index("ix_defects_property_id", "defects", ["property_id"])
    op.create_index("ix_defects_component_id", "defects", ["component_id"])
    _enable_tenant_rls("defects")

    op.create_table(
        "warranties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("warranty_reference", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(255), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=True),
        sa.Column("warranty_type", sa.String(128), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=False),
        sa.Column("terms_reference", sa.String(255), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "VOID", name="warrantystatus"), nullable=False),
        *_provenance_columns(),
    )
    op.create_index("ix_warranties_organisation_id", "warranties", ["organisation_id"])
    op.create_index("ix_warranties_expiry_date", "warranties", ["expiry_date"])
    op.create_index("ix_warranties_development_id", "warranties", ["development_id"])
    op.create_index("ix_warranties_building_id", "warranties", ["building_id"])
    op.create_index("ix_warranties_property_id", "warranties", ["property_id"])
    op.create_index("ix_warranties_component_id", "warranties", ["component_id"])
    _enable_tenant_rls("warranties")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_warranties ON warranties")
    op.drop_table("warranties")
    op.execute("DROP TYPE IF EXISTS warrantystatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_defects ON defects")
    op.drop_table("defects")
    op.execute("DROP TYPE IF EXISTS defectstatus")
    op.execute("DROP TYPE IF EXISTS defectseverity")
