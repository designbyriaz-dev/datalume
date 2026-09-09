"""Tenancies — architecture/05-commercial-domain.md §1: Tenant, Lease.

Revision ID: 0018_tenancies
Revises: 0017_stock_condition_planned_investment
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_tenancies"
down_revision: Union[str, None] = "0017_stock_condition_planned_investment"
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
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_details", postgresql.JSONB, nullable=False, server_default="{}"),
        *_provenance_columns(),
    )
    op.create_index("ix_tenants_organisation_id", "tenants", ["organisation_id"])
    _tenant_rls("tenants")

    op.create_table(
        "leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lease_reference", sa.String(32), nullable=False),
        sa.Column("lease_start", sa.Date, nullable=False),
        sa.Column("lease_expiry", sa.Date, nullable=False),
        sa.Column("break_date", sa.Date, nullable=True),
        sa.Column("rent_review_date", sa.Date, nullable=True),
        sa.Column("contractual_rent_pence", sa.Integer, nullable=False),
        sa.Column("rent_frequency", sa.Enum("WEEKLY", "MONTHLY", "QUARTERLY", "ANNUALLY", name="rentfrequency"), nullable=False),
        sa.Column("service_charge_amount_pence", sa.Integer, nullable=True),
        sa.Column(
            "occupancy_status",
            sa.Enum("OCCUPIED", "VACANT", "NOTICE_GIVEN", name="occupancystatus"),
            nullable=False,
        ),
        sa.Column(
            "lease_status",
            sa.Enum("DRAFT", "ACTIVE", "EXPIRED", "TERMINATED", "RENEWED", name="leasestatus"),
            nullable=False,
        ),
        *_provenance_columns(),
    )
    op.create_index("ix_leases_organisation_id", "leases", ["organisation_id"])
    op.create_index("ix_leases_property_id", "leases", ["property_id"])
    op.create_index("ix_leases_tenant_id", "leases", ["tenant_id"])
    _tenant_rls("leases")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_leases ON leases")
    op.drop_table("leases")
    op.execute("DROP TYPE IF EXISTS leasestatus")
    op.execute("DROP TYPE IF EXISTS occupancystatus")
    op.execute("DROP TYPE IF EXISTS rentfrequency")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_tenants ON tenants")
    op.drop_table("tenants")
