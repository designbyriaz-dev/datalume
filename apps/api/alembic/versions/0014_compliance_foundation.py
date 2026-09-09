"""Compliance Framework foundation — architecture/04-operations-domain.md §3.

Revision ID: 0014_compliance_foundation
Revises: 0013_repairs
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_compliance_foundation"
down_revision: Union[str, None] = "0013_repairs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _global_or_org_rls(table_name: str) -> None:
    # Same non-standard RLS as component_types (Sprint 8): NULL
    # organisation_id rows are the DataLume-seeded global catalog,
    # visible to every org, so the standard tenant-isolation policy
    # (which would hide NULL rows once a tenant context is set) doesn't
    # apply here.
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table_name} ON {table_name}
        USING (
            organisation_id IS NULL
            OR organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "compliance_frameworks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_compliance_frameworks_organisation_id", "compliance_frameworks", ["organisation_id"])
    _global_or_org_rls("compliance_frameworks")

    op.create_table(
        "compliance_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_frameworks.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
    )
    op.create_index("ix_compliance_domains_organisation_id", "compliance_domains", ["organisation_id"])
    op.create_index("ix_compliance_domains_framework_id", "compliance_domains", ["framework_id"])
    _global_or_org_rls("compliance_domains")

    op.create_table(
        "compliance_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_domains.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cadence", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("superseded_date", sa.Date, nullable=True),
    )
    op.create_index("ix_compliance_requirements_organisation_id", "compliance_requirements", ["organisation_id"])
    op.create_index("ix_compliance_requirements_domain_id", "compliance_requirements", ["domain_id"])
    _global_or_org_rls("compliance_requirements")

    op.create_table(
        "requirement_applicability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_requirements.id"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("applicable_from", sa.Date, nullable=False),
        sa.Column("applicable_to", sa.Date, nullable=True),
        sa.Column("basis", sa.String(255), nullable=True),
    )
    op.create_index("ix_requirement_applicability_organisation_id", "requirement_applicability", ["organisation_id"])
    op.create_index("ix_requirement_applicability_requirement_id", "requirement_applicability", ["requirement_id"])
    op.create_index(
        "ix_requirement_applicability_entity", "requirement_applicability", ["entity_type", "entity_id"]
    )

    op.execute("ALTER TABLE requirement_applicability ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE requirement_applicability FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_requirement_applicability ON requirement_applicability
        USING (
            organisation_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_requirement_applicability ON requirement_applicability")
    op.drop_table("requirement_applicability")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_compliance_requirements ON compliance_requirements")
    op.drop_table("compliance_requirements")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_compliance_domains ON compliance_domains")
    op.drop_table("compliance_domains")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_compliance_frameworks ON compliance_frameworks")
    op.drop_table("compliance_frameworks")
