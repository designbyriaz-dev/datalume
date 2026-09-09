"""Development hierarchy: developments, buildings, floors — and wiring
properties/spaces into it — architecture/03-development-domain.md §1.

Revision ID: 0006_hierarchy
Revises: 0005_properties
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_hierarchy"
down_revision: Union[str, None] = "0005_properties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["developments", "buildings", "floors"]


def _provenance_columns() -> list[sa.Column]:
    """Mirrors app/core/provenance.py's ProvenanceMixin — see 0005's
    identical helper. sourcetype ENUM already exists (created in 0005);
    SQLAlchemy reuses it by name here rather than re-emitting CREATE TYPE,
    same as it already does across properties/spaces in that migration."""
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
        "developments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("development_reference", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("postcode", sa.String(16), nullable=True),
        sa.Column("region", sa.String(128), nullable=True),
        sa.Column("developer", sa.String(255), nullable=True),
        sa.Column("principal_designer", sa.String(255), nullable=True),
        sa.Column("principal_contractor", sa.String(255), nullable=True),
        sa.Column("employer_agent", sa.String(255), nullable=True),
        sa.Column("number_of_planned_properties", sa.Integer, nullable=True),
        sa.Column("planned_start_date", sa.Date, nullable=True),
        sa.Column("planned_completion_date", sa.Date, nullable=True),
        sa.Column("actual_completion_date", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "CONCEPT", "DESIGN", "PRE_CONSTRUCTION", "CONSTRUCTION", "HANDOVER", "COMPLETED",
                "OPERATIONAL", "CANCELLED", name="developmentstatus",
            ),
            nullable=False,
        ),
        sa.Column("planning_reference", sa.String(64), nullable=True),
        sa.Column("building_control_reference", sa.String(64), nullable=True),
        sa.Column("bsr_reference", sa.String(64), nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_developments_organisation_id", "developments", ["organisation_id"])

    op.create_table(
        "buildings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
        sa.Column("building_reference", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("building_type", sa.String(64), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("height", sa.Float, nullable=True),
        sa.Column("storeys", sa.Integer, nullable=True),
        sa.Column("construction_type", sa.String(128), nullable=True),
        sa.Column("planned_completion", sa.Date, nullable=True),
        sa.Column("actual_completion", sa.Date, nullable=True),
        sa.Column("building_control_reference", sa.String(64), nullable=True),
        sa.Column("bsr_reference", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PLANNED", "UNDER_CONSTRUCTION", "COMPLETED", "OPERATIONAL", name="buildingstatus"),
            nullable=False,
        ),
        *_provenance_columns(),
    )
    op.create_index("ix_buildings_organisation_id", "buildings", ["organisation_id"])
    op.create_index("ix_buildings_development_id", "buildings", ["development_id"])

    op.create_table(
        "floors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("level_index", sa.Integer, nullable=True),
        *_provenance_columns(),
    )
    op.create_index("ix_floors_organisation_id", "floors", ["organisation_id"])
    op.create_index("ix_floors_building_id", "floors", ["building_id"])

    op.add_column(
        "properties",
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id"), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("floor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("floors.id"), nullable=True),
    )

    op.alter_column("spaces", "property_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column(
        "spaces",
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
    )
    op.create_check_constraint(
        "ck_space_has_a_parent", "spaces", "property_id IS NOT NULL OR building_id IS NOT NULL"
    )

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
    op.drop_constraint("ck_space_has_a_parent", "spaces", type_="check")
    op.drop_column("spaces", "building_id")
    op.alter_column("spaces", "property_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_column("properties", "floor_id")
    op.drop_column("properties", "building_id")
    op.drop_column("properties", "development_id")

    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("floors")
    op.drop_table("buildings")
    op.drop_table("developments")
    op.execute("DROP TYPE IF EXISTS buildingstatus")
    op.execute("DROP TYPE IF EXISTS developmentstatus")
