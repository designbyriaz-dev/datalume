"""Properties, spaces, data_health_findings — architecture/03-development-domain.md §1
and architecture/02-data-platform.md §5. First real consumers of
ProvenanceMixin (Sprint 3).

Revision ID: 0005_properties
Revises: 0004_documents
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_properties"
down_revision: Union[str, None] = "0004_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["properties", "spaces", "data_health_findings"]


def _provenance_columns() -> list[sa.Column]:
    """Mirrors app/core/provenance.py's ProvenanceMixin exactly — see that
    module's docstring for why every domain table gets these."""
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
    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_reference", sa.String(32), nullable=False),
        sa.Column("uprn", sa.String(32), nullable=True),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("postcode", sa.String(16), nullable=True),
        sa.Column("property_type", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PLANNED", "UNDER_CONSTRUCTION", "READY_FOR_HANDOVER", "HANDED_OVER", "OPERATIONAL",
                "VOID", "OCCUPIED", "DISPOSED", name="propertystatus",
            ),
            nullable=False,
        ),
        *_provenance_columns(),
    )
    op.create_index("ix_properties_organisation_id", "properties", ["organisation_id"])

    op.create_table(
        "spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("space_type", sa.String(64), nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_spaces_organisation_id", "spaces", ["organisation_id"])
    op.create_index("ix_spaces_property_id", "spaces", ["property_id"])

    op.create_table(
        "data_health_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("check_code", sa.String(64), nullable=False),
        sa.Column(
            "severity", sa.Enum("LOW", "MEDIUM", "HIGH", name="findingseverity"), nullable=False
        ),
        sa.Column("affected_entity_type", sa.String(64), nullable=False),
        sa.Column("affected_entity_id", sa.String(64), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_data_health_findings_organisation_id", "data_health_findings", ["organisation_id"])

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
    op.drop_table("data_health_findings")
    op.drop_table("spaces")
    op.drop_table("properties")
    op.execute("DROP TYPE IF EXISTS findingseverity")
    op.execute("DROP TYPE IF EXISTS propertystatus")
    op.execute("DROP TYPE IF EXISTS sourcetype")
