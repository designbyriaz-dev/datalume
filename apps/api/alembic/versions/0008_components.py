"""Component register: component_types, components — architecture/03-development-domain.md §2.

Revision ID: 0008_components
Revises: 0007_identifiers
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_components"
down_revision: Union[str, None] = "0007_identifiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "component_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Nullable, unlike every other organisation_id in this schema:
        # NULL rows are the global seeded catalog, visible to every org
        # (same "system row" pattern as roles, migration 0001 — see the
        # RLS policy below, which is deliberately NOT the standard
        # tenant-isolation one for exactly this reason).
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("parent_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("component_types.id"), nullable=True),
    )
    op.create_index("ix_component_types_organisation_id", "component_types", ["organisation_id"])

    op.execute("ALTER TABLE component_types ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE component_types FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_component_types ON component_types
        USING (
            organisation_id IS NULL
            OR organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )

    op.create_table(
        "components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=True),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id"), nullable=True),
        sa.Column("parent_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=True),
        sa.Column("component_reference", sa.String(32), nullable=False),
        sa.Column("component_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("component_types.id"), nullable=False),
        sa.Column("component_subtype", sa.String(128), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("installer", sa.String(255), nullable=True),
        sa.Column("installation_date", sa.Date, nullable=True),
        sa.Column("commissioning_date", sa.Date, nullable=True),
        sa.Column("warranty_start", sa.Date, nullable=True),
        sa.Column("warranty_expiry", sa.Date, nullable=True),
        sa.Column("expected_life_years", sa.Integer, nullable=True),
        sa.Column("indicative_replacement_date", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REPLACED", "DISPOSED", name="componentstatus"),
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
    op.create_index("ix_components_organisation_id", "components", ["organisation_id"])
    op.create_index("ix_components_parent_component_id", "components", ["parent_component_id"])

    op.execute("ALTER TABLE components ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE components FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_components ON components
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_components ON components")
    op.drop_table("components")
    op.execute("DROP TYPE IF EXISTS componentstatus")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_component_types ON component_types")
    op.drop_table("component_types")
