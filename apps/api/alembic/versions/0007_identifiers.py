"""Identifier & Reference Engine: external_references, reference_patterns
— architecture/03-development-domain.md §3.

Replaces the plain nullable columns used for external identifiers since
Sprint 5/6 (properties.uprn, developments.{planning_reference,
building_control_reference, bsr_reference}, buildings.
{building_control_reference, bsr_reference}) with the real
external_references model — including the hard write-path constraint
(a CHECK that source_type can never be SYSTEM_GENERATED on that table).

Revision ID: 0007_identifiers
Revises: 0006_hierarchy
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_identifiers"
down_revision: Union[str, None] = "0006_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["external_references", "reference_patterns"]


def upgrade() -> None:
    op.create_table(
        "external_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column(
            "reference_type",
            sa.Enum(
                "UPRN", "PLANNING_REFERENCE", "BUILDING_CONTROL_REFERENCE", "BSR_REFERENCE",
                "DEVELOPER_PLOT_NUMBER", "CONTRACTOR_REFERENCE", "MANUFACTURER_SERIAL_NUMBER",
                "LAND_REGISTRY_REFERENCE", name="externalreferencetype",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(255), nullable=False),
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
        sa.CheckConstraint(
            "source_type IN ('MANUAL', 'FILE_UPLOAD', 'API', 'INTEGRATION')",
            name="ck_external_reference_never_system_generated",
        ),
    )
    op.create_index("ix_external_references_organisation_id", "external_references", ["organisation_id"])
    op.create_index(
        "ix_external_references_entity", "external_references", ["organisation_id", "entity_type", "entity_id"]
    )

    op.create_table(
        "reference_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("pattern", sa.String(128), nullable=False),
        sa.Column("next_sequence", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organisation_id", "entity_type", name="uq_reference_pattern_org_entity"),
    )
    op.create_index("ix_reference_patterns_organisation_id", "reference_patterns", ["organisation_id"])

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

    op.drop_column("properties", "uprn")
    op.drop_column("developments", "planning_reference")
    op.drop_column("developments", "building_control_reference")
    op.drop_column("developments", "bsr_reference")
    op.drop_column("buildings", "building_control_reference")
    op.drop_column("buildings", "bsr_reference")


def downgrade() -> None:
    op.add_column("buildings", sa.Column("bsr_reference", sa.String(64), nullable=True))
    op.add_column("buildings", sa.Column("building_control_reference", sa.String(64), nullable=True))
    op.add_column("developments", sa.Column("bsr_reference", sa.String(64), nullable=True))
    op.add_column("developments", sa.Column("building_control_reference", sa.String(64), nullable=True))
    op.add_column("developments", sa.Column("planning_reference", sa.String(64), nullable=True))
    op.add_column("properties", sa.Column("uprn", sa.String(32), nullable=True))

    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("reference_patterns")
    op.drop_table("external_references")
    op.execute("DROP TYPE IF EXISTS externalreferencetype")
